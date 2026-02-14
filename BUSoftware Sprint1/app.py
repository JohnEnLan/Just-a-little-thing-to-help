import _deps  # noqa: F401

from threading import Lock
from datetime import timedelta

from flask import (
    Flask,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)

from anomaly_detector import run_detection
from models import AnomalyRecord, Building, EnergyReading, db, utcnow_naive
from seed_data import generate_demo_metrics, seed_database

app = Flask(__name__)
app.config["SECRET_KEY"] = "green-campus-sprint-1"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///campus.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

demo_sync_lock = Lock()
last_demo_sync_hour = None

ESTIMATED_CO2_KG_PER_KWH = 0.18
ESTIMATED_COST_GBP_PER_KWH = 0.28


def estimate_metrics(electricity_kwh: float) -> dict:
    return {
        "estimated_co2_kg": round(electricity_kwh * ESTIMATED_CO2_KG_PER_KWH, 3),
        "estimated_cost_gbp": round(electricity_kwh * ESTIMATED_COST_GBP_PER_KWH, 2),
    }


def serialize_building(building: Building) -> dict:
    return {
        "id": building.id,
        "name": building.name,
        "location": building.location,
    }


def serialize_reading(reading: EnergyReading) -> dict:
    payload = {
        "timestamp": reading.timestamp.strftime("%Y-%m-%dT%H:%M:%S"),
        "electricity_kwh": reading.electricity_kwh,
    }
    payload.update(estimate_metrics(reading.electricity_kwh))
    return payload


def serialize_anomaly(anomaly: AnomalyRecord) -> dict:
    payload = {
        "timestamp": anomaly.timestamp.strftime("%Y-%m-%dT%H:%M:%S"),
        "electricity_kwh": anomaly.electricity_kwh,
        "anomaly_score": anomaly.anomaly_score,
    }
    payload.update(estimate_metrics(anomaly.electricity_kwh or 0.0))
    return payload


def build_dashboard_cards(buildings: list[Building]) -> list[dict]:
    cards: list[dict] = []
    for building in buildings:
        latest_reading = (
            EnergyReading.query.filter_by(building_id=building.id)
            .order_by(EnergyReading.timestamp.desc())
            .first()
        )
        anomaly_count = AnomalyRecord.query.filter_by(building_id=building.id).count()

        cards.append(
            {
                "id": building.id,
                "name": building.name,
                "location": building.location or "Unknown location",
                "capacity_kw": building.capacity_kw,
                "latest_reading": latest_reading.electricity_kwh if latest_reading else None,
                "latest_timestamp": (
                    latest_reading.timestamp.strftime("%Y-%m-%d %H:%M")
                    if latest_reading
                    else None
                ),
                "anomaly_count": anomaly_count,
            }
        )

    return cards


def sync_demo_data(current_hour=None) -> dict:
    sync_to_hour = (current_hour or utcnow_naive()).replace(
        minute=0,
        second=0,
        microsecond=0,
    )
    created_readings = 0
    affected_buildings: set[int] = set()

    if Building.query.count() == 0 or EnergyReading.query.count() == 0:
        seed_database(reset=True)
        created_readings = EnergyReading.query.count()
        affected_buildings = {building.id for building in Building.query.all()}

    for building in Building.query.order_by(Building.id.asc()).all():
        latest_reading = (
            EnergyReading.query.filter_by(building_id=building.id)
            .order_by(EnergyReading.timestamp.desc())
            .first()
        )
        if latest_reading is None:
            continue

        next_timestamp = latest_reading.timestamp + timedelta(hours=1)
        while next_timestamp <= sync_to_hour:
            electricity_kwh, water_litre = generate_demo_metrics(building, next_timestamp)
            db.session.add(
                EnergyReading(
                    building_id=building.id,
                    timestamp=next_timestamp,
                    electricity_kwh=electricity_kwh,
                    water_litre=water_litre,
                )
            )
            created_readings += 1
            affected_buildings.add(building.id)
            next_timestamp += timedelta(hours=1)

    if created_readings:
        db.session.commit()

    if affected_buildings:
        for building_id in sorted(affected_buildings):
            run_detection(building_id)

    return {
        "synced_to_hour": sync_to_hour,
        "created_readings": created_readings,
        "affected_buildings": sorted(affected_buildings),
    }


def ensure_demo_data_current() -> None:
    global last_demo_sync_hour

    current_hour = utcnow_naive().replace(minute=0, second=0, microsecond=0)
    if last_demo_sync_hour is not None and last_demo_sync_hour >= current_hour:
        return

    with demo_sync_lock:
        if last_demo_sync_hour is not None and last_demo_sync_hour >= current_hour:
            return

        sync_demo_data(current_hour)
        last_demo_sync_hour = current_hour


with app.app_context():
    db.create_all()
    if Building.query.count() == 0:
        seed_database(reset=False)
    ensure_demo_data_current()


@app.before_request
def auto_refresh_demo_dataset():
    if request.endpoint in {None, "static", "picture_of_uob"}:
        return

    ensure_demo_data_current()


@app.route("/")
def index():
    return redirect(url_for("dashboard"))


@app.route("/assets/picture-of-uob.svg")
def picture_of_uob():
    return send_from_directory(app.root_path, "PictureOfUOB.svg", mimetype="image/svg+xml")


@app.route("/dashboard")
def dashboard():
    buildings = Building.query.order_by(Building.name.asc()).all()

    today_start = utcnow_naive().replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_start = today_start + timedelta(days=1)

    stats = {
        "total_buildings": len(buildings),
        "total_readings": EnergyReading.query.count(),
        "total_anomalies": AnomalyRecord.query.count(),
        "anomalies_today": AnomalyRecord.query.filter(
            AnomalyRecord.detected_at >= today_start,
            AnomalyRecord.detected_at < tomorrow_start,
        ).count(),
    }

    return render_template(
        "dashboard.html",
        building_cards=build_dashboard_cards(buildings),
        stats=stats,
        auto_refresh_note="Demo data and anomaly detection update automatically every hour.",
    )


@app.route("/building/<int:building_id>")
def building(building_id: int):
    building = db.session.get(Building, building_id)
    if building is None:
        abort(404)

    readings_count = EnergyReading.query.filter_by(building_id=building_id).count()
    anomaly_count = AnomalyRecord.query.filter_by(building_id=building_id).count()
    latest_reading = (
        EnergyReading.query.filter_by(building_id=building_id)
        .order_by(EnergyReading.timestamp.desc())
        .first()
    )

    return render_template(
        "building.html",
        building=building,
        readings_count=readings_count,
        anomaly_count=anomaly_count,
        auto_refresh_note="Demo data and anomaly detection update automatically every hour.",
        conversion_factors={
            "estimated_co2_kg_per_kwh": ESTIMATED_CO2_KG_PER_KWH,
            "estimated_cost_gbp_per_kwh": ESTIMATED_COST_GBP_PER_KWH,
        },
        latest_reading_label=(
            latest_reading.timestamp.strftime("%Y-%m-%d %H:%M")
            if latest_reading
            else "No readings yet"
        ),
    )


@app.route("/api/buildings")
def api_buildings():
    buildings = Building.query.order_by(Building.name.asc()).all()
    return jsonify([serialize_building(building) for building in buildings])


@app.route("/api/buildings/<int:building_id>/readings")
def api_building_readings(building_id: int):
    building = db.session.get(Building, building_id)
    if building is None:
        return jsonify({"error": "Building not found"}), 404

    readings = (
        EnergyReading.query.filter_by(building_id=building_id)
        .order_by(EnergyReading.timestamp.asc())
        .all()
    )

    return jsonify(
        {
            "building_id": building.id,
            "building_name": building.name,
            "conversion_factors": {
                "estimated_co2_kg_per_kwh": ESTIMATED_CO2_KG_PER_KWH,
                "estimated_cost_gbp_per_kwh": ESTIMATED_COST_GBP_PER_KWH,
            },
            "readings": [serialize_reading(reading) for reading in readings],
        }
    )


@app.route("/api/buildings/<int:building_id>/anomalies")
def api_building_anomalies(building_id: int):
    building = db.session.get(Building, building_id)
    if building is None:
        return jsonify({"error": "Building not found"}), 404

    anomalies = (
        AnomalyRecord.query.filter_by(building_id=building_id)
        .order_by(AnomalyRecord.timestamp.asc())
        .all()
    )

    return jsonify(
        {
            "building_id": building.id,
            "anomalies": [serialize_anomaly(anomaly) for anomaly in anomalies],
        }
    )


@app.route("/api/buildings/<int:building_id>/detect", methods=["POST"])
def api_detect_anomalies(building_id: int):
    building = db.session.get(Building, building_id)
    if building is None:
        return jsonify({"error": "Building not found"}), 404

    try:
        results = run_detection(building_id)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    return jsonify(
        {
            "status": "ok",
            "anomalies_found": len(results),
            "results": results,
        }
    )


if __name__ == "__main__":
    app.run(port=5000, debug=True)

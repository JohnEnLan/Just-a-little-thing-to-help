import _deps  # noqa: F401

from threading import Lock
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from sqlalchemy.exc import IntegrityError
from werkzeug.utils import secure_filename

from anomaly_detector import run_detection
from models import (
    AnomalyRecord,
    Building,
    EnergyReading,
    Suggestion,
    SuggestionLike,
    db,
    utcnow_naive,
)
from seed_data import generate_demo_metrics, seed_database

app = Flask(__name__)
app.config["SECRET_KEY"] = "green-campus-sprint-1"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///campus.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 6 * 1024 * 1024

db.init_app(app)

demo_sync_lock = Lock()
last_demo_sync_hour = None

ESTIMATED_CO2_KG_PER_KWH = 0.18
ESTIMATED_COST_GBP_PER_KWH = 0.28
ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
SUGGESTION_UPLOAD_SUBDIR = Path("uploads") / "suggestions"
SUGGESTION_UPLOAD_DIR = Path(app.root_path) / "static" / SUGGESTION_UPLOAD_SUBDIR
SUGGESTION_SORT_OPTIONS = {
    "likes": "Most liked",
    "latest": "Latest",
}


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


def allowed_image_file(filename: str) -> bool:
    if "." not in filename:
        return False
    return filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


def save_uploaded_suggestion_image(file_storage) -> str:
    filename = secure_filename(file_storage.filename or "")
    if not filename or not allowed_image_file(filename):
        raise ValueError("Only JPG, JPEG, PNG, and WEBP images are allowed.")

    extension = filename.rsplit(".", 1)[1].lower()
    SUGGESTION_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    stored_name = f"{uuid4().hex}.{extension}"
    destination = SUGGESTION_UPLOAD_DIR / stored_name
    file_storage.save(destination)
    return (SUGGESTION_UPLOAD_SUBDIR / stored_name).as_posix()


def get_client_ip() -> str:
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()[:255]
    return (request.remote_addr or "unknown")[:255]


def get_suggestion_like_count(suggestion_id: int) -> int:
    return SuggestionLike.query.filter_by(suggestion_id=suggestion_id).count()


def normalize_suggestion_sort(sort_mode: str | None) -> str:
    if sort_mode in SUGGESTION_SORT_OPTIONS:
        return sort_mode
    return "likes"


def build_feedback_page_context(client_ip: str, sort_mode: str) -> tuple[list[dict], dict]:
    liked_ids = {
        row.suggestion_id
        for row in SuggestionLike.query.with_entities(SuggestionLike.suggestion_id)
        .filter_by(ip_address=client_ip)
        .all()
    }

    like_counts_subquery = (
        db.session.query(
            SuggestionLike.suggestion_id.label("suggestion_id"),
            db.func.count(SuggestionLike.id).label("like_count"),
        )
        .group_by(SuggestionLike.suggestion_id)
        .subquery()
    )

    like_count_column = db.func.coalesce(like_counts_subquery.c.like_count, 0)
    suggestion_query = (
        db.session.query(
            Suggestion,
            like_count_column.label("like_count"),
        )
        .outerjoin(
            like_counts_subquery,
            like_counts_subquery.c.suggestion_id == Suggestion.id,
        )
    )

    if sort_mode == "latest":
        suggestion_query = suggestion_query.order_by(
            Suggestion.created_at.desc(),
            like_count_column.desc(),
        )
    else:
        suggestion_query = suggestion_query.order_by(
            like_count_column.desc(),
            Suggestion.created_at.desc(),
        )

    suggestion_rows = suggestion_query.all()

    suggestion_cards: list[dict] = []
    total_likes = 0
    for suggestion, like_count in suggestion_rows:
        current_like_count = int(like_count or 0)
        total_likes += current_like_count

        suggestion_cards.append(
            {
                "suggestion": suggestion,
                "like_count": current_like_count,
                "created_label": suggestion.created_at.strftime("%Y-%m-%d %H:%M"),
                "image_url": (
                    url_for("static", filename=suggestion.image_path)
                    if suggestion.image_path
                    else None
                ),
                "user_liked": suggestion.id in liked_ids,
            }
        )

    latest_suggestion = Suggestion.query.order_by(Suggestion.created_at.desc()).first()
    stats = {
        "total_suggestions": len(suggestion_cards),
        "total_likes": total_likes,
        "latest_submission": (
            latest_suggestion.created_at.strftime("%Y-%m-%d %H:%M")
            if latest_suggestion
            else "No suggestions yet"
        ),
    }
    return suggestion_cards, stats


def render_feedback_page(
    *,
    form_data: dict | None = None,
    form_errors: list[str] | None = None,
    current_sort: str = "likes",
    status_code: int = 200,
):
    normalized_sort = normalize_suggestion_sort(current_sort)
    suggestion_cards, feedback_stats = build_feedback_page_context(
        get_client_ip(),
        normalized_sort,
    )

    return (
        render_template(
            "feedback.html",
            suggestion_cards=suggestion_cards,
            feedback_stats=feedback_stats,
            form_data=form_data or {},
            form_errors=form_errors or [],
            current_sort=normalized_sort,
            sort_options=SUGGESTION_SORT_OPTIONS,
            allowed_image_extensions=", ".join(
                extension.upper() for extension in sorted(ALLOWED_IMAGE_EXTENSIONS)
            ),
        ),
        status_code,
    )


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
    SUGGESTION_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
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


@app.route("/feedback")
def feedback():
    return render_feedback_page(
        current_sort=normalize_suggestion_sort(request.args.get("sort")),
    )


@app.route("/feedback/submit", methods=["POST"])
def feedback_submit():
    sort_mode = normalize_suggestion_sort(request.form.get("sort"))
    title = request.form.get("title", "").strip()
    content = request.form.get("content", "").strip()
    image = request.files.get("image")

    form_data = {
        "title": title,
        "content": content,
    }
    form_errors: list[str] = []

    if not title:
        form_errors.append("Title is required.")
    if not content:
        form_errors.append("Content is required.")

    has_image = image is not None and bool(image.filename)
    if has_image and not allowed_image_file(image.filename or ""):
        form_errors.append("Only JPG, JPEG, PNG, and WEBP images are allowed.")

    if form_errors:
        return render_feedback_page(
            form_data=form_data,
            form_errors=form_errors,
            current_sort=sort_mode,
            status_code=400,
        )

    image_path = None
    if has_image:
        try:
            image_path = save_uploaded_suggestion_image(image)
        except ValueError as exc:
            return render_feedback_page(
                form_data=form_data,
                form_errors=[str(exc)],
                current_sort=sort_mode,
                status_code=400,
            )
        except OSError:
            return render_feedback_page(
                form_data=form_data,
                form_errors=["Image upload failed. Please try again."],
                current_sort=sort_mode,
                status_code=500,
            )

    db.session.add(
        Suggestion(
            title=title,
            content=content,
            image_path=image_path,
        )
    )

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()

        if image_path:
            uploaded_file = Path(app.static_folder or "") / image_path
            if uploaded_file.exists():
                uploaded_file.unlink()

        return render_feedback_page(
            form_data=form_data,
            form_errors=["Suggestion submission failed. Please try again."],
            current_sort=sort_mode,
            status_code=500,
        )

    flash("Suggestion submitted successfully.", "success")
    return redirect(url_for("feedback", sort=sort_mode))


@app.route("/api/buildings")
def api_buildings():
    buildings = Building.query.order_by(Building.name.asc()).all()
    return jsonify([serialize_building(building) for building in buildings])


@app.route("/api/dashboard/electricity-overview")
def api_dashboard_electricity_overview():
    buildings = Building.query.order_by(Building.name.asc()).all()
    latest_timestamp = db.session.query(db.func.max(EnergyReading.timestamp)).scalar()

    if latest_timestamp is None:
        return jsonify(
            {
                "window_hours": 24 * 7,
                "buildings": [],
            }
        )

    window_hours = 24 * 7
    window_start = latest_timestamp - timedelta(hours=window_hours - 1)
    building_series: list[dict] = []

    for building in buildings:
        readings = (
            EnergyReading.query.filter(
                EnergyReading.building_id == building.id,
                EnergyReading.timestamp >= window_start,
                EnergyReading.timestamp <= latest_timestamp,
            )
            .order_by(EnergyReading.timestamp.asc())
            .all()
        )
        anomalies = (
            AnomalyRecord.query.filter(
                AnomalyRecord.building_id == building.id,
                AnomalyRecord.timestamp >= window_start,
                AnomalyRecord.timestamp <= latest_timestamp,
            )
            .order_by(AnomalyRecord.timestamp.asc())
            .all()
        )

        building_series.append(
            {
                "id": building.id,
                "name": building.name,
                "readings": [serialize_reading(reading) for reading in readings],
                "anomalies": [serialize_anomaly(anomaly) for anomaly in anomalies],
            }
        )

    return jsonify(
        {
            "window_hours": window_hours,
            "window_start": window_start.strftime("%Y-%m-%dT%H:%M:%S"),
            "window_end": latest_timestamp.strftime("%Y-%m-%dT%H:%M:%S"),
            "buildings": building_series,
        }
    )


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


@app.route("/api/suggestions/<int:suggestion_id>/like", methods=["POST"])
def api_like_suggestion(suggestion_id: int):
    suggestion = db.session.get(Suggestion, suggestion_id)
    if suggestion is None:
        return jsonify({"error": "Suggestion not found"}), 404

    client_ip = get_client_ip()
    existing_like = SuggestionLike.query.filter_by(
        suggestion_id=suggestion_id,
        ip_address=client_ip,
    ).first()
    if existing_like is not None:
        return jsonify(
            {
                "status": "duplicate",
                "message": "You have already liked this suggestion.",
                "like_count": get_suggestion_like_count(suggestion_id),
            }
        ), 409

    db.session.add(
        SuggestionLike(
            suggestion_id=suggestion_id,
            ip_address=client_ip,
        )
    )

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(
            {
                "status": "duplicate",
                "message": "You have already liked this suggestion.",
                "like_count": get_suggestion_like_count(suggestion_id),
            }
        ), 409

    return jsonify(
        {
            "status": "ok",
            "message": "Suggestion liked.",
            "like_count": get_suggestion_like_count(suggestion_id),
        }
    )


@app.errorhandler(413)
def request_entity_too_large(_error):
    if request.path.startswith("/feedback"):
        flash("Image upload failed. Files must be 6 MB or smaller.", "error")
        return redirect(
            url_for(
                "feedback",
                sort=normalize_suggestion_sort(request.args.get("sort")),
            )
        )

    return jsonify({"error": "Uploaded file is too large."}), 413


if __name__ == "__main__":
    app.run(port=5000, debug=True)

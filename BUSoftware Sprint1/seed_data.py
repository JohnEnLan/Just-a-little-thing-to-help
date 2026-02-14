import _deps  # noqa: F401

import math
import random
from datetime import timedelta

from models import Building, EnergyReading, db, utcnow_naive


def generate_demo_metrics(building: Building, timestamp) -> tuple[float, float]:
    rng = random.Random(f"{building.id}-{timestamp.isoformat()}")
    hour = timestamp.hour
    weekday = timestamp.weekday()

    is_working_day = weekday < 5
    is_active_window = 8 <= hour < 18

    base_ratio = 0.58 if is_active_window else 0.18
    if not is_working_day:
        base_ratio *= 0.7

    seasonal_adjustment = 1 + 0.06 * math.sin((timestamp.timetuple().tm_yday / 365) * math.tau)
    noise = rng.uniform(-0.08, 0.08) * building.capacity_kw
    electricity_kwh = max(building.capacity_kw * base_ratio * seasonal_adjustment + noise, 5.0)

    # Deterministic spikes keep the demo visually interesting for anomaly detection.
    if rng.random() < 0.04:
        electricity_kwh *= rng.uniform(2.2, 3.3)

    water_base = 950 if is_active_window else 260
    if not is_working_day:
        water_base *= 0.8

    water_litre = max(water_base + rng.uniform(-90, 90), 40.0)
    return round(electricity_kwh, 2), round(water_litre, 2)


def seed_database(reset: bool = True) -> bool:
    if reset:
        db.drop_all()

    db.create_all()

    if not reset and Building.query.count() > 0:
        return False

    buildings = [
        Building(
            name="Engineering Block A",
            location="North Campus",
            capacity_kw=180.0,
        ),
        Building(
            name="Library",
            location="Central Campus",
            capacity_kw=140.0,
        ),
        Building(
            name="Science Lab",
            location="South Campus",
            capacity_kw=220.0,
        ),
    ]

    db.session.add_all(buildings)
    db.session.flush()

    total_hours = 30 * 24
    start_time = utcnow_naive().replace(minute=0, second=0, microsecond=0) - timedelta(
        days=30
    )

    for building in buildings:
        anomaly_slots = set(random.sample(range(total_hours), k=random.randint(3, 5)))

        for slot in range(total_hours):
            current_time = start_time + timedelta(hours=slot)
            electricity_kwh, water_litre = generate_demo_metrics(building, current_time)

            if slot in anomaly_slots:
                electricity_kwh = round(
                    electricity_kwh * random.uniform(2.4, 3.4),
                    2,
                )

            db.session.add(
                EnergyReading(
                    building_id=building.id,
                    timestamp=current_time,
                    electricity_kwh=round(electricity_kwh, 2),
                    water_litre=round(water_litre, 2),
                )
            )

    db.session.commit()
    return True


if __name__ == "__main__":
    from app import app

    with app.app_context():
        created = seed_database(reset=True)
        if created:
            print("Database seeded successfully with 3 buildings and 30 days of data.")

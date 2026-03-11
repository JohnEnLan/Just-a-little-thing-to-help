import _deps  # noqa: F401

import numpy as np
from sklearn.ensemble import IsolationForest

from models import AnomalyRecord, EnergyReading, db, utcnow_naive


def run_detection(building_id: int) -> list[dict]:
    readings = (
        EnergyReading.query.filter_by(building_id=building_id)
        .order_by(EnergyReading.timestamp.asc())
        .all()
    )
    if not readings:
        return []

    data = np.array([[reading.electricity_kwh] for reading in readings])

    model = IsolationForest(contamination=0.05, random_state=42)
    predictions = model.fit_predict(data)
    scores = model.decision_function(data)

    AnomalyRecord.query.filter_by(building_id=building_id).delete()

    detected_at = utcnow_naive()
    anomalies_found: list[dict] = []

    for index, prediction in enumerate(predictions):
        if prediction != -1:
            continue

        reading = readings[index]
        score = float(scores[index])

        anomaly = AnomalyRecord(
            building_id=building_id,
            reading_id=reading.id,
            timestamp=reading.timestamp,
            electricity_kwh=reading.electricity_kwh,
            anomaly_score=score,
            detected_at=detected_at,
        )
        db.session.add(anomaly)

        anomalies_found.append(
            {
                "timestamp": reading.timestamp.strftime("%Y-%m-%dT%H:%M:%S"),
                "electricity_kwh": reading.electricity_kwh,
                "anomaly_score": score,
            }
        )

    db.session.commit()
    return anomalies_found

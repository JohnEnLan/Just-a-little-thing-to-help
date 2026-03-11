import _deps  # noqa: F401

from datetime import UTC, datetime

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Building(db.Model):
    __tablename__ = "buildings"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Text, nullable=False)
    location = db.Column(db.Text)
    capacity_kw = db.Column(db.Float)

    readings = db.relationship("EnergyReading", backref="building", lazy=True)
    anomalies = db.relationship("AnomalyRecord", backref="building", lazy=True)


class EnergyReading(db.Model):
    __tablename__ = "energy_readings"

    id = db.Column(db.Integer, primary_key=True)
    building_id = db.Column(db.Integer, db.ForeignKey("buildings.id"))
    timestamp = db.Column(db.DateTime, nullable=False)
    electricity_kwh = db.Column(db.Float, nullable=False)
    water_litre = db.Column(db.Float)


class AnomalyRecord(db.Model):
    __tablename__ = "anomaly_records"

    id = db.Column(db.Integer, primary_key=True)
    building_id = db.Column(db.Integer, db.ForeignKey("buildings.id"))
    reading_id = db.Column(db.Integer, db.ForeignKey("energy_readings.id"))
    timestamp = db.Column(db.DateTime, nullable=False)
    electricity_kwh = db.Column(db.Float)
    anomaly_score = db.Column(db.Float)
    detected_at = db.Column(db.DateTime, default=utcnow_naive)

    reading = db.relationship("EnergyReading", backref="anomaly_records")


class Suggestion(db.Model):
    __tablename__ = "suggestions"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.Text, nullable=False)
    content = db.Column(db.Text, nullable=False)
    image_path = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=utcnow_naive, nullable=False, index=True)
    updated_at = db.Column(
        db.DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )

    likes = db.relationship(
        "SuggestionLike",
        backref="suggestion",
        lazy=True,
        cascade="all, delete-orphan",
    )


class SuggestionLike(db.Model):
    __tablename__ = "suggestion_likes"
    __table_args__ = (
        db.UniqueConstraint(
            "suggestion_id",
            "ip_address",
            name="uq_suggestion_like_ip",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    suggestion_id = db.Column(
        db.Integer,
        db.ForeignKey("suggestions.id"),
        nullable=False,
        index=True,
    )
    ip_address = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow_naive, nullable=False)

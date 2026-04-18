# models.py
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Building(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    location = db.Column(db.String(100), nullable=False)
    readings = db.relationship('EnergyReading', backref='building', lazy=True)
    anomalies = db.relationship('AnomalyRecord', backref='building', lazy=True)

class EnergyReading(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    building_id = db.Column(db.Integer, db.ForeignKey('building.id'), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    electricity_kwh = db.Column(db.Float, nullable=False)

class AnomalyRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    building_id = db.Column(db.Integer, db.ForeignKey('building.id'), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False)
    electricity_kwh = db.Column(db.Float, nullable=False)
    anomaly_score = db.Column(db.Float, nullable=False)
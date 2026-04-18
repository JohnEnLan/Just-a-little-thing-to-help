from flask import redirect, url_for, render_template, jsonify,flash,request
from app import app,db
from app.models import Building, EnergyReading, AnomalyRecord
from anomaly_detector import run_detection
from seed_data import seed_database


@app.route('/')
def index(num=[0]):
    print("Loading......")
    if num[-1]==0:
        seed_database()
        num.append(1)
    return redirect(url_for('dashboard'))


@app.route('/dashboard')
def dashboard():
    buildings = Building.query.all()
    return render_template('dashboard.html', buildings=buildings)


@app.route('/building/<int:building_id>')
def building(building_id):
    building = Building.query.get_or_404(building_id)
    buildings = Building.query.all()
    readings_data=[]
    anomalies_data=[]
    dict=[]
    
    if building:        
        readings = EnergyReading.query.filter_by(building_id=building_id).order_by(EnergyReading.timestamp.asc()).all()
        for r in readings:
            readings_data.append(
            {
                "timestamp": r.timestamp.strftime("%Y-%m-%dT%H:%M:%S"),
                "electricity_kwh": r.electricity_kwh
            })
        
        try:
            results = run_detection(building_id)

            dict={"status": "ok","anomalies_found": len(results),"results": results}
                            
        except Exception as e:
            dict={"status:":"Error","anomalies_found":1,"results":[]}
            
        anomalies = AnomalyRecord.query.filter_by(building_id=building_id).order_by(AnomalyRecord.timestamp.asc()).all()

        for a in anomalies:
            anomalies_data.append(
                {
                    "timestamp": a.timestamp.strftime("%Y-%m-%dT%H:%M:%S"),
                    "electricity_kwh": a.electricity_kwh,
                    "anomaly_score": a.anomaly_score
                })

    return render_template('building.html',buildings=buildings,building=building,readings_data=readings_data,anomalies_data=anomalies_data,dict=dict)
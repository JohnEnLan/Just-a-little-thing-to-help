from flask import Flask, redirect, url_for, render_template, jsonify
from models import db, Building, EnergyReading, AnomalyRecord  # 严格按照要求导入模型
from anomaly_detector import run_detection  # 严格按照要求导入检测方法

app = Flask(__name__)

# 配置数据库 (SQLite) 和 SQLAlchemy
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///campus.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# 初始化 DB
db.init_app(app)

# 在应用启动时自动创建数据库表
with app.app_context():
    db.create_all()


# ==========================================
# 页面路由 (Page Routes)
# ==========================================

@app.route('/')
def index():
    """GET / -> Redirect to /dashboard"""
    return redirect(url_for('dashboard'))


@app.route('/dashboard')
def dashboard():
    """GET /dashboard -> Render templates/dashboard.html"""
    buildings = Building.query.all()
    return render_template('dashboard.html', buildings=buildings)


@app.route('/building/<int:building_id>')
def building(building_id):
    """GET /building/<int:building_id> -> Render templates/building.html"""
    building = Building.query.get_or_404(building_id)
    return render_template('building.html', building=building)


# ==========================================
# API 路由 (API Routes)
# ==========================================

@app.route('/api/buildings')
def api_buildings():
    """GET /api/buildings -> Return JSON list of all buildings"""
    buildings = Building.query.all()
    results = [
        {"id": b.id, "name": b.name, "location": b.location}
        for b in buildings
    ]
    return jsonify(results)


@app.route('/api/buildings/<int:building_id>/readings')
def api_building_readings(building_id):
    """GET /api/buildings/<id>/readings -> Returns 30-day readings JSON"""
    building = Building.query.get(building_id)
    if not building:
        return jsonify({"error": "not found"}), 404

    # 查询该建筑的所有读数并按时间升序排列
    readings = EnergyReading.query.filter_by(building_id=building_id) \
        .order_by(EnergyReading.timestamp.asc()) \
        .all()

    readings_data = [
        {
            # 严格使用 ISO 8601 格式
            "timestamp": r.timestamp.strftime("%Y-%m-%dT%H:%M:%S"),
            "electricity_kwh": r.electricity_kwh
        }
        for r in readings
    ]

    return jsonify({
        "building_id": building.id,
        "building_name": building.name,
        "readings": readings_data
    })


@app.route('/api/buildings/<int:building_id>/anomalies')
def api_building_anomalies(building_id):
    """GET /api/buildings/<id>/anomalies -> Returns anomaly records JSON"""
    building = Building.query.get(building_id)
    if not building:
        return jsonify({"error": "not found"}), 404

    # 查询该建筑的所有异常记录并按时间升序排列
    anomalies = AnomalyRecord.query.filter_by(building_id=building_id) \
        .order_by(AnomalyRecord.timestamp.asc()) \
        .all()

    anomalies_data = [
        {
            "timestamp": a.timestamp.strftime("%Y-%m-%dT%H:%M:%S"),
            "electricity_kwh": a.electricity_kwh,
            "anomaly_score": a.anomaly_score
        }
        for a in anomalies
    ]

    return jsonify({
        "building_id": building.id,
        "anomalies": anomalies_data
    })


@app.route('/api/buildings/<int:building_id>/detect', methods=['POST'])
def api_detect_anomalies(building_id):
    """POST /api/buildings/<id>/detect -> Trigger anomaly detection"""
    building = Building.query.get(building_id)
    if not building:
        return jsonify({"error": "not found"}), 404

    try:
        # 调用 anomaly_detector.py 中的算法，它会在内部处理数据库写入
        results = run_detection(building_id)

        return jsonify({
            "status": "ok",
            "anomalies_found": len(results),
            "results": results
        })
    except Exception as e:
        # 如果检测算法抛出异常，返回 500 错误
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    # 强制在 5000 端口运行并开启 debug 模式
    app.run(port=5000, debug=True)
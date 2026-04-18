# anomaly_detector.py
from models import db, EnergyReading, AnomalyRecord
from sklearn.ensemble import IsolationForest
import numpy as np
from datetime import datetime


def run_detection(building_id: int) -> list[dict]:
    # 1. 查询该建筑的所有能耗数据
    readings = EnergyReading.query.filter_by(building_id=building_id).order_by(EnergyReading.timestamp.asc()).all()
    if not readings:
        return []

    # 2. 准备 scikit-learn 训练数据
    data = np.array([[r.electricity_kwh] for r in readings])

    # 3. 使用 Isolation Forest 进行异常检测
    model = IsolationForest(contamination=0.05, random_state=42)
    model.fit(data)

    # 预测结果：-1 为异常，1 为正常。并获取异常分数
    predictions = model.predict(data)
    scores = model.decision_function(data)

    # 4. 清理旧的异常记录 (可选，为保证多次点击不重复积累过时数据)
    AnomalyRecord.query.filter_by(building_id=building_id).delete()

    anomalies_found = []

    # 5. 找出异常点并存入数据库
    for i, pred in enumerate(predictions):
        if pred == -1:
            reading = readings[i]
            score = float(scores[i])

            # 创建异常记录
            anomaly = AnomalyRecord(
                building_id=building_id,
                timestamp=reading.timestamp,
                electricity_kwh=reading.electricity_kwh,
                anomaly_score=score
            )
            db.session.add(anomaly)

            # 格式化返回结果
            anomalies_found.append({
                "timestamp": reading.timestamp.strftime("%Y-%m-%dT%H:%M:%S"),
                "electricity_kwh": reading.electricity_kwh,
                "anomaly_score": score
            })

    # 提交数据库事务
    db.session.commit()

    return anomalies_found
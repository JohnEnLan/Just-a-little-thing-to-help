import random
from datetime import datetime, timedelta
from app import app,db
from app.models import Building, EnergyReading


def seed_database():
    with app.app_context():
        # 清空现有数据
        db.drop_all()
        db.create_all()

        # 创建 3 栋建筑
        buildings = [
            Building(name="Engineering Block A", location="North Campus"),
            Building(name="Library", location="Central Campus"),
            Building(name="Science Lab", location="South Campus")
        ]
        db.session.add_all(buildings)
        db.session.commit()

        # 生成过去 30 天的数据 (每小时一条)
        start_time = datetime.now() - timedelta(days=30)

        for building in buildings:
            for day in range(30):
                for hour in range(24):
                    current_time = start_time + timedelta(days=day, hours=hour)

                    # 模拟正常能耗 (基准 + 随机波动)
                    base_kwh = 100 if 8 <= hour <= 18 else 30  # 白天高，夜间低
                    kwh = base_kwh + random.uniform(-10, 10)

                    # 随机注入异常 (大约 2% 的概率)
                    if random.random() < 0.02:
                        kwh = base_kwh * random.uniform(2.5, 4.0)  # 异常偏高

                    reading = EnergyReading(
                        building_id=building.id,
                        timestamp=current_time,
                        electricity_kwh=round(kwh, 2)
                    )
                    db.session.add(reading)

        db.session.commit()
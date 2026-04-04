import psycopg2
import os

# Вставь сюда свой External Database URL
DATABASE_URL = "postgresql://postgres1:RrBVKWJuBLjwIyLuSU5qBOGIKpPGqQDI@dpg-d6s37lf5r7bs7387ntrg-a.frankfurt-postgres.render.com/volunteer_db_udj4"

# Читаем SQL файл
with open('volounter_db.sql', 'r', encoding='utf-8') as f:
    sql = f.read()

# Подключаемся и выполняем
conn = psycopg2.connect(DATABASE_URL)
cursor = conn.cursor()

try:
    cursor.execute(sql)
    conn.commit()
    print("✅ Таблицы успешно созданы!")
except Exception as e:
    print(f"❌ Ошибка: {e}")
    conn.rollback()
finally:
    cursor.close()
    conn.close()
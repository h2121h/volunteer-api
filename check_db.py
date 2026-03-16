import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Загружаем .env файл
load_dotenv()

# Получаем строку подключения
DATABASE_URL = os.getenv("DATABASE_URL")
print(f"Пробуем подключиться к: {DATABASE_URL}")

try:
    # Создаем подключение
    engine = create_engine(DATABASE_URL)

    # Пробуем выполнить запрос
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1")).scalar()
        print(f"✅ Подключение успешно! Результат: {result}")

        # Получаем список таблиц
        tables = conn.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)).fetchall()

        print(f"\n📊 Найдено таблиц: {len(tables)}")
        for table in tables:
            print(f"   - {table[0]}")

except Exception as e:
    print(f"❌ Ошибка подключения: {e}")

    # Дополнительная диагностика
    print("\n🔍 Диагностика:")
    print("1. Убедитесь, что PostgreSQL запущен")
    print("2. Проверьте, что база данных 'volunteer_db' существует")
    print("3. Проверьте, что пароль '1234' правильный")
    print("4. Попробуйте подключиться через pgAdmin")
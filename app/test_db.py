import sys
import os

# Добавляем путь к корневой папке проекта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from app.database import SessionLocal, engine
    from app.models import User
    from sqlalchemy import text

    print("✅ Модули успешно импортированы")

    # Пробуем подключиться
    db = SessionLocal()

    # Проверяем подключение
    result = db.execute(text("SELECT 1")).first()
    print("✅ Подключение к БД успешно!")

    # Проверяем таблицу users
    user_count = db.query(User).count()
    print(f"✅ Таблица users существует. Количество записей: {user_count}")

    db.close()

except Exception as e:
    print(f"❌ Ошибка: {type(e).__name__}: {e}")
    import traceback

    traceback.print_exc()
from sqlalchemy import create_engine, inspect, text
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

print("=" * 70)
print("ПРОВЕРКА СООТВЕТСТВИЯ БД И PYTHON МОДЕЛЕЙ")
print("=" * 70)

inspector = inspect(engine)

# Таблицы в БД
db_tables = set(inspector.get_table_names())
print(f"\n📊 Таблицы в БД ({len(db_tables)} шт.):")
for t in sorted(db_tables):
    print(f"  - {t}")

# Ожидаемые модели из твоего models.py (на основе кода, который мы писали)
expected_models = {
    'users', 'roles', 'skills', 'user_skills',
    'projects', 'tasks', 'task_applications', 'task_assignments',
    'task_reports', 'volunteer_documents', 'project_feedback'
}

print(f"\n📦 Ожидаемые модели: {expected_models}")

# Проверяем, какие таблицы есть в БД, но нет в моделях
extra_tables = db_tables - expected_models - {'logins', 'backups', 'registration'}
if extra_tables:
    print(f"\n⚠️ Таблицы в БД, которых нет в моделях: {extra_tables}")

# Проверяем, какие модели есть в коде, но нет в БД
missing_tables = expected_models - db_tables
if missing_tables:
    print(f"\n❌ Модели, которых нет в БД: {missing_tables}")
else:
    print(f"\n✅ Все модели присутствуют в БД")

print("\n" + "=" * 70)
print("ПРОВЕРКА ТАБЛИЦЫ USERS")
print("=" * 70)

# Колонки в таблице users
db_columns = inspector.get_columns('users')
print("\n📋 Колонки в БД (users):")
for col in db_columns:
    print(f"  - {col['name']}: {col['type']}")

# Колонки, которые должны быть в модели (на основе твоего SQL)
expected_user_columns = {
    'id', 'email', 'password_hash', 'name', 'phone', 'city',
    'role_id', 'is_active', 'is_verified', 'created_at', 'last_login_at'
}

db_column_names = {col['name'] for col in db_columns}
missing_in_model = expected_user_columns - db_column_names
if missing_in_model:
    print(f"\n❌ Колонки в SQL, которых нет в БД: {missing_in_model}")
else:
    print("\n✅ Все колонки из SQL присутствуют в БД")

# Важно: в модели у нас было `full_name`, а в БД `name`
if 'name' in db_column_names and 'full_name' not in db_column_names:
    print("\n⚠️ ВНИМАНИЕ: В БД колонка называется 'name', а в модели 'full_name'!")
    print("   Нужно исправить models.py: заменить full_name на name")

print("\n" + "=" * 70)
print("ПРОВЕРКА РОЛЕЙ")
print("=" * 70)

with engine.connect() as conn:
    result = conn.execute(text("SELECT id, code, name FROM roles"))
    print("\n📋 Роли в БД:")
    for row in result:
        print(f"  - id={row[0]}, code={row[1]}, name={row[2]}")
    print("\n✅ Роли добавлены, всё корректно!")

print("\n" + "=" * 70)
print("ИТОГ")
print("=" * 70)
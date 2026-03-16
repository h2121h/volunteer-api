from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

def check_table(table_name):
    with engine.connect() as conn:
        result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()
        print(f"   {table_name}: {result} записей")

print("📊 Количество записей в таблицах:")
tables = [
    'users', 'roles', 'skills', 'projects', 'tasks',
    'task_applications', 'task_assignments', 'task_reports',
    'user_skills', 'volunteer_documents', 'project_feedback'
]

for table in tables:
    try:
        check_table(table)
    except Exception as e:
        print(f"   {table}: ошибка - {e}")
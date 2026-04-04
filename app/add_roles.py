import psycopg2

# External Database URL со скриншота
DATABASE_URL = "postgresql://postgres1:RrBVKWJuBLjwIyLuSU5qBOGIKpPGqQDI@dpg-d6s37lf5r7bs7387ntrg-a.frankfurt-postgres.render.com/volunteer_db_udj4"

roles = [
    ('volunteer', 'Волонтёр'),
    ('organizer', 'Организатор'),
    ('curator', 'Куратор'),
    ('admin', 'Администратор'),
]

try:
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()

    for code, name in roles:
        cursor.execute(
            "INSERT INTO roles (code, name) VALUES (%s, %s) ON CONFLICT (code) DO NOTHING",
            (code, name)
        )

    conn.commit()
    print("✅ Роли успешно добавлены!")

    # Проверка
    cursor.execute("SELECT * FROM roles")
    print("\n📋 Роли в базе данных:")
    for row in cursor.fetchall():
        print(f"  - id={row[0]}, code={row[1]}, name={row[2]}")

    cursor.close()
    conn.close()

except Exception as e:
    print(f"❌ Ошибка: {e}")
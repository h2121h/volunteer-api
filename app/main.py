from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Volunteer API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"message": "API работает"}

@app.get("/api/stats")
def get_stats():
    return {
        "volunteers_count": 15,
        "tasks_completed": 42,
        "projects_count": 5,
        "open_tasks": 8,
        "pending_reports": 3
    }

@app.get("/api/projects")
def get_projects():
    return [
        {
            "id": 1,
            "name": "Помощь пожилым",
            "description": "Помощь пожилым людям",
            "status": "active"
        },
        {
            "id": 2,
            "name": "Забота о животных",
            "description": "Помощь приюту",
            "status": "active"
        }
    ]

@app.get("/api/tasks")
def get_tasks():
    return [
        {
            "id": 1,
            "title": "Выгул собак",
            "location": "Приют",
            "task_date": "15.04.2025",
            "task_time": "15:00",
            "volunteers_needed": 3
        },
        {
            "id": 2,
            "title": "Уборка территории",
            "location": "Парк",
            "task_date": "16.04.2025",
            "task_time": "10:00",
            "volunteers_needed": 5
        }
    ]

@app.post("/api/register")
def register(data: dict):
    return {"success": True, "message": "Регистрация успешна!"}

@app.post("/api/login")
def login(data: dict):
    return {
        "success": True,
        "message": "Вход выполнен успешно",
        "token": "fake-jwt-token-12345",
        "name": data.get("email", "Пользователь").split('@')[0]
    }

@app.get("/api/check_auth")
def check_auth():
    return {"authenticated": False}

@app.post("/api/logout")
def logout():
    return {"success": True, "message": "Вы вышли из системы"}

@app.post("/api/tasks/{task_id}/join")
def join_task(task_id: int):
    return {"success": True, "message": "Вы успешно записались на задачу!"}

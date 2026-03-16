from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import users, tasks, reports, site_api

app = FastAPI(title="Volunteer API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users.router)
app.include_router(tasks.router)
app.include_router(reports.router)
app.include_router(site_api.router)

@app.get("/")
def root():
    return {"message": "Волонтерское API работает"}
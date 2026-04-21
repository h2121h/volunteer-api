"""
FastAPI main.py — обновлённый для задания 4+5.
Подключаем CQRS, BFF, Domain Events, Metrics.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="VolunteersOS API",
    description="Volunteer platform API with CQRS, BFF, Domain Events",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Существующие роутеры ─────────────────────────────────────────────────────
from app.routers import (
    checkins, tasks_extra, reports_router,
    projects_api, admin, stats,
    bff_mobile, bff_web, bff_desktop,
)
app.include_router(checkins.router)
app.include_router(tasks_extra.router)
app.include_router(reports_router.router)
app.include_router(projects_api.router)
app.include_router(admin.router)
app.include_router(stats.router)
app.include_router(bff_mobile.router)
app.include_router(bff_web.router)
app.include_router(bff_desktop.router)

# ── НОВЫЕ: CQRS + Metrics + Domain Events (задание 4+5) ──────────────────────
from app.routers import cqrs_commands, cqrs_queries, hotspot_metrics

app.include_router(cqrs_commands.router)    # POST /cmd/*
app.include_router(cqrs_queries.router)     # GET  /query/*
app.include_router(hotspot_metrics.router)  # GET  /metrics/*


@app.on_event("startup")
async def startup():
    """Запускаем Domain Event subscriber при старте."""
    from app.routers.domain_events import subscriber
    subscriber.start()


@app.get("/health")
def health():
    return {"status": "ok", "version": "2.0.0"}

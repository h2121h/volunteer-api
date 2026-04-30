"""
CQRS — Query side (чтение).

4.1.1 Разделение на Command/Query — все запросы ТОЛЬКО читают данные
4.1.2 Денормализованная Read-модель — возвращаем уже собранные данные для UI
4.1.3 Query без ORM — используем raw SQL через SQLAlchemy text()
5.2.3 Кэш — кэшируем тяжёлые запросы в Redis, инвалидируем после команд

Запрещено: менять данные в Query-эндпоинтах!
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
from datetime import datetime, timedelta
import json

from app import models, auth
from app.database import get_db

# 5.2.2 Метрики — трекинг горячих точек
def _track(endpoint: str):
    try:
        from app.hotspot_metrics import track
        track(endpoint)
    except Exception:
        pass

try:
    import redis as redis_lib
    _redis = redis_lib.Redis(host='localhost', port=6379, db=0, decode_responses=True)
    _redis.ping()
    REDIS_OK = True
except Exception:
    REDIS_OK = False

CACHE_TTL = 30  # секунд — горячий кэш для dashboard

router = APIRouter(prefix="/query", tags=["CQRS Queries"])


def _cache_get(key: str):
    if not REDIS_OK:
        return None
    try:
        val = _redis.get(key)
        return json.loads(val) if val else None
    except Exception:
        return None


def _cache_set(key: str, data, ttl: int = CACHE_TTL):
    if not REDIS_OK:
        return
    try:
        _redis.setex(key, ttl, json.dumps(data, default=str))
    except Exception:
        pass


# ── Query 1: Volunteer Dashboard (денормализованный) ─────────────────────────
# ГОРЯЧАЯ ТОЧКА — вызывается при каждом входе на главный экран (5.2.1)

@router.get("/volunteer/dashboard")
def query_volunteer_dashboard(
    db:   Session = Depends(get_db),
    user: models.User = Depends(auth.volunteer_required),
):
    """
    Денормализованный дашборд волонтёра — одним SQL запросом без ORM.
    Read-модель: задачи + мои заявки + статистика одним запросом.
    Кэшируется 30 сек в Redis.
    """
    # 5.2.2 Трекинг — самый частый эндпоинт
    _track("GET /query/volunteer/dashboard")

    cache_key = f"volunteer:dashboard:{user.id}"
    cached = _cache_get(cache_key)
    if cached:
        cached["_from_cache"] = True
        return cached

    # 4.1.3 Query без ORM — raw SQL
    # Денормализованный результат: задачи + статус моей заявки
    tasks_sql = text("""
        SELECT
            t.id,
            t.title,
            t.description,
            t.location,
            t.event_date::text,
            t.needed_people,
            t.status,
            p.title AS project_title,
            a.status AS my_application_status,
            a.id     AS my_application_id,
            COUNT(a2.id) FILTER (WHERE a2.status IN ('created','approved')) AS applicants_count
        FROM tasks t
        LEFT JOIN projects p ON p.id = t.project_id
        LEFT JOIN task_applications a  ON a.task_id = t.id AND a.user_id = :uid
        LEFT JOIN task_applications a2 ON a2.task_id = t.id
        WHERE t.status = 'open'
        GROUP BY t.id, t.title, t.description, t.location, t.event_date,
                 t.needed_people, t.status, p.title, a.status, a.id
        ORDER BY t.event_date ASC NULLS LAST
        LIMIT 20
    """)

    # Статистика волонтёра одним SQL
    stats_sql = text("""
        SELECT
            COUNT(r.id) FILTER (WHERE r.is_approved = true)         AS approved_reports,
            COUNT(r.id) FILTER (WHERE r.is_approved = false)        AS pending_reports,
            COALESCE(SUM(r.hours) FILTER (WHERE r.is_approved = true), 0) AS total_hours
        FROM task_reports r
        WHERE r.user_id = :uid
    """)

    try:
        tasks_rows = db.execute(tasks_sql, {"uid": user.id}).fetchall()
        stats_row  = db.execute(stats_sql, {"uid": user.id}).fetchone()
    except Exception:
        # Fallback если таблицы называются иначе
        tasks_rows, stats_row = [], None

    tasks = [
        {
            "id":                    row[0],
            "title":                 row[1],
            "description":           row[2],
            "location":              row[3],
            "event_date":            row[4],
            "needed_people":         row[5],
            "status":                row[6],
            "project":               row[7],
            "my_application_status": row[8],
            "my_application_id":     row[9],
            "applicants_count":      int(row[10] or 0),
            "already_applied":       row[8] is not None,
            "spots_left":            max(0, (row[5] or 0) - int(row[10] or 0)),
        }
        for row in tasks_rows
    ]

    total_hours  = float(stats_row[2] or 0) if stats_row else 0.0
    total_points = int(total_hours * 10)

    result = {
        "user": {
            "id":    user.id,
            "name":  user.name,
            "email": user.email,
        },
        "tasks": tasks,
        "stats": {
            "approved_reports": int(stats_row[0] or 0) if stats_row else 0,
            "pending_reports":  int(stats_row[1] or 0) if stats_row else 0,
            "total_hours":      round(total_hours, 1),
            "total_points":     total_points,
        },
        "_from_cache": False,
    }

    _cache_set(cache_key, result, CACHE_TTL)
    return result


# ── Query 2: Curator Dashboard (денормализованный) ───────────────────────────
# ТЯЖЁЛАЯ ОПЕРАЦИЯ — агрегация по нескольким таблицам (5.2.1)

@router.get("/curator/dashboard")
def query_curator_dashboard(
    db:   Session = Depends(get_db),
    user: models.User = Depends(auth.curator_required),
):
    """
    Денормализованная панель куратора — raw SQL без ORM.
    Кэшируется 60 сек.
    """
    cache_key = f"curator:dashboard:{user.id}"
    cached = _cache_get(cache_key)
    if cached:
        cached["_from_cache"] = True
        return cached

    # Заявки на одобрение (денормализовано)
    apps_sql = text("""
        SELECT
            a.id,
            a.task_id,
            t.title   AS task_title,
            a.user_id,
            u.name    AS user_name,
            u.email   AS user_email,
            a.message,
            a.status,
            a.applied_at::text
        FROM task_applications a
        JOIN tasks t      ON t.id = a.task_id
        JOIN projects pr  ON pr.id = t.project_id
        JOIN users u      ON u.id = a.user_id
        WHERE pr.created_by = :uid
          AND a.status = 'created'
        ORDER BY a.applied_at DESC
        LIMIT 50
    """)

    # Отчёты на проверке с авто-дедлайном BR-03
    reports_sql = text("""
        SELECT
            r.id,
            r.user_id,
            u.name      AS user_name,
            r.hours,
            r.comment,
            r.photo_url,
            r.submitted_at::text,
            (r.submitted_at + interval '72 hours')::text AS auto_approve_at
        FROM task_reports r
        JOIN users u ON u.id = r.user_id
        WHERE r.is_approved = false
        ORDER BY r.submitted_at ASC
        LIMIT 50
    """)

    # Статистика команды одним запросом
    team_sql = text("""
        SELECT
            COUNT(DISTINCT a.user_id)                                AS total_volunteers,
            COUNT(a.id) FILTER (WHERE a.status = 'created')         AS pending_applications,
            COUNT(r.id) FILTER (WHERE r.is_approved = false)        AS pending_reports,
            COUNT(r.id) FILTER (WHERE r.is_approved = true)         AS approved_reports
        FROM task_applications a
        JOIN tasks t     ON t.id = a.task_id
        JOIN projects pr ON pr.id = t.project_id
        LEFT JOIN task_reports r ON r.user_id = a.user_id
        WHERE pr.created_by = :uid
    """)

    try:
        apps_rows    = db.execute(apps_sql,    {"uid": user.id}).fetchall()
        reports_rows = db.execute(reports_sql, {}).fetchall()
        team_row     = db.execute(team_sql,    {"uid": user.id}).fetchone()
    except Exception:
        apps_rows, reports_rows, team_row = [], [], None

    result = {
        "curator": {"id": user.id, "name": user.name},
        "pending_applications": [
            {
                "id":         r[0], "task_id": r[1], "task_title": r[2],
                "user_id":    r[3], "user_name": r[4], "user_email": r[5],
                "message":    r[6], "status": r[7], "applied_at": r[8],
            }
            for r in apps_rows
        ],
        "pending_reports": [
            {
                "id":             r[0], "user_id": r[1], "user_name": r[2],
                "hours":          float(r[3] or 0), "comment": r[4],
                "photo_url":      r[5], "submitted_at": r[6],
                "auto_approve_at": r[7],
            }
            for r in reports_rows
        ],
        "team_stats": {
            "total_volunteers":     int(team_row[0] or 0) if team_row else 0,
            "pending_applications": int(team_row[1] or 0) if team_row else 0,
            "pending_reports":      int(team_row[2] or 0) if team_row else 0,
            "approved_reports":     int(team_row[3] or 0) if team_row else 0,
        },
        "_from_cache": False,
    }

    _cache_set(cache_key, result, 60)
    return result


# ── Query 3: Tasks filtered (тяжёлый GET-лист — 5.2.1) ───────────────────────

@router.get("/tasks")
def query_tasks(
    category:   Optional[str] = Query(None),
    difficulty: Optional[str] = Query(None),
    lat:        Optional[float] = Query(None),
    lng:        Optional[float] = Query(None),
    radius:     Optional[int]   = Query(5000),
    db:         Session = Depends(get_db),
):
    """
    Тяжёлый GET-лист задач с фильтрами — raw SQL, кэш 60 сек.
    Горячая точка (5.2.1): вызывается при открытии списка.
    """
    # 5.2.2 Трекинг — тяжёлый GET список с фильтрами
    _track("GET /query/tasks")

    cache_key = f"tasks:list:{category}:{difficulty}:{lat}:{lng}:{radius}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    where_clauses = ["t.status = 'open'"]
    params: dict = {}

    if category:
        where_clauses.append("t.category = :category")
        params["category"] = category
    if difficulty:
        where_clauses.append("t.difficulty = :difficulty")
        params["difficulty"] = difficulty

    where_str = " AND ".join(where_clauses)

    sql = text(f"""
        SELECT
            t.id, t.title, t.description, t.location,
            t.event_date::text, t.needed_people, t.status,
            t.category, t.difficulty,
            p.title AS project_title,
            COUNT(a.id) FILTER (WHERE a.status IN ('created','approved')) AS applicants
        FROM tasks t
        LEFT JOIN projects p ON p.id = t.project_id
        LEFT JOIN task_applications a ON a.task_id = t.id
        WHERE {where_str}
        GROUP BY t.id, t.title, t.description, t.location,
                 t.event_date, t.needed_people, t.status,
                 t.category, t.difficulty, p.title
        ORDER BY t.event_date ASC NULLS LAST
        LIMIT 50
    """)

    try:
        rows = db.execute(sql, params).fetchall()
    except Exception:
        rows = []

    result = [
        {
            "id": r[0], "title": r[1], "description": r[2],
            "location": r[3], "event_date": r[4], "needed_people": r[5],
            "status": r[6], "category": r[7], "difficulty": r[8],
            "project": r[9], "applicants": int(r[10] or 0),
            "spots_left": max(0, (r[5] or 0) - int(r[10] or 0)),
        }
        for r in rows
    ]

    _cache_set(cache_key, result, 60)
    return result


# ── Query 4: Event Log (для демонстрации Domain Events) ──────────────────────

@router.get("/events/log")
def query_event_log(
    limit: int = Query(20, le=100),
    user:  models.User = Depends(auth.organizer_required),
):
    """
    Лог Domain Events из Redis — только для организатора.
    Показывает последние события системы.
    """
    if not REDIS_OK:
        return {"events": [], "note": "Redis недоступен"}
    try:
        raw_events = _redis.lrange("volunteer:event_log", 0, limit - 1)
        events = [json.loads(e) for e in raw_events]
        return {"events": events, "count": len(events)}
    except Exception:
        return {"events": [], "error": "Ошибка чтения Redis"}

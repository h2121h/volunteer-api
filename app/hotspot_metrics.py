"""
5.2 Тепловая карта — горячие точки, метрики, кэш.

5.2.1 Определение горячих точек:
  - GET /query/volunteer/dashboard — самый частый (каждый вход в приложение)
  - GET /query/tasks — тяжёлый список с фильтрами
  - POST /cmd/tasks/{id}/apply — тяжёлая команда (BR-01/BR-05)
  - Worker generate_volunteer_report — тяжёлая фоновая операция

5.2.2 Метрики — счётчики в Redis
5.2.3 Кэш — TTL-кэш, инвалидация после команд
"""
from fastapi import APIRouter, Request, Depends
from typing import Optional
import time
import json

from app import models, auth

try:
    import redis as redis_lib
    _redis = redis_lib.Redis(host='localhost', port=6379, db=0, decode_responses=True)
    _redis.ping()
    REDIS_OK = True
except Exception:
    REDIS_OK = False

router = APIRouter(prefix="/metrics", tags=["Metrics & Hotspots"])

# Горячие точки — описание для документации
HOTSPOTS = {
    "GET /query/volunteer/dashboard": {
        "type":        "query",
        "description": "Дашборд волонтёра — вызывается при каждом входе",
        "cache_ttl":   30,
        "category":    "hot_read",
    },
    "GET /query/curator/dashboard": {
        "type":        "query",
        "description": "Дашборд куратора — тяжёлая агрегация",
        "cache_ttl":   60,
        "category":    "heavy_read",
    },
    "GET /query/tasks": {
        "type":        "query",
        "description": "Список задач с фильтрами",
        "cache_ttl":   60,
        "category":    "hot_read",
    },
    "POST /cmd/tasks/{id}/apply": {
        "type":        "command",
        "description": "Записаться на задачу — BR-01/BR-05 проверки",
        "cache_ttl":   None,
        "category":    "heavy_command",
    },
    "Worker: generate_volunteer_report": {
        "type":        "worker",
        "description": "Генерация PDF — вынесена в очередь",
        "cache_ttl":   None,
        "category":    "heavy_worker",
    },
}


def track_request(endpoint: str):
    """5.2.2 Метрика: инкрементируем счётчик обращений к эндпоинту."""
    if not REDIS_OK:
        return
    try:
        key = f"metrics:calls:{endpoint}"
        _redis.incr(key)
        _redis.expire(key, 86400)  # сбрасываем через 24ч

        # Храним топ-эндпоинтов в sorted set
        _redis.zincrby("metrics:hotspots", 1, endpoint)
    except Exception:
        pass


def invalidate_cache(user_id: int, scope: str = "dashboard"):
    """5.2.3 Инвалидация кэша после команды."""
    if not REDIS_OK:
        return
    try:
        keys = [
            f"volunteer:dashboard:{user_id}",
            f"curator:dashboard:{user_id}",
            "tasks:list:*",
        ]
        for k in keys:
            if "*" in k:
                for match in _redis.scan_iter(k):
                    _redis.delete(match)
            else:
                _redis.delete(k)
    except Exception:
        pass


@router.get("/hotspots")
def get_hotspots(user: models.User = Depends(auth.organizer_required)):
    """
    5.2.1 Тепловая карта — горячие точки с реальными счётчиками из Redis.
    Показывает самые частые запросы.
    """
    result = {}

    for endpoint, meta in HOTSPOTS.items():
        calls = 0
        if REDIS_OK:
            try:
                safe_key = endpoint.replace("/", ":").replace("{", "").replace("}", "").replace(" ", "_")
                calls = int(_redis.get(f"metrics:calls:{safe_key}") or 0)
            except Exception:
                pass
        result[endpoint] = {**meta, "calls_today": calls}

    # Топ из Redis sorted set
    top_endpoints = []
    if REDIS_OK:
        try:
            top = _redis.zrevrange("metrics:hotspots", 0, 9, withscores=True)
            top_endpoints = [{"endpoint": e, "calls": int(s)} for e, s in top]
        except Exception:
            pass

    return {
        "hotspots":      result,
        "top_endpoints": top_endpoints,
        "cache_stats": {
            "strategy": "Redis TTL cache",
            "hot_read_ttl":   "30 сек (dashboard)",
            "heavy_read_ttl": "60 сек (lists, aggregations)",
            "invalidation":   "После каждой команды (approve/reject/apply)",
        },
        "worker_tasks": {
            "generate_volunteer_report": "Тяжёлая — вынесена в Redis Queue",
            "send_welcome_notification": "Лёгкая — уведомление",
            "send_approval_notification": "Лёгкая — уведомление",
        },
    }


@router.get("/cache/stats")
def get_cache_stats(user: models.User = Depends(auth.curator_required)):
    """5.2.3 Статистика кэша Redis."""
    if not REDIS_OK:
        return {"status": "Redis недоступен"}
    try:
        info = _redis.info("stats")
        memory = _redis.info("memory")
        cached_keys = len(_redis.keys("volunteer:dashboard:*")) + \
                      len(_redis.keys("curator:dashboard:*")) + \
                      len(_redis.keys("tasks:list:*"))
        return {
            "status":         "OK",
            "cached_dashboards": cached_keys,
            "hits":           info.get("keyspace_hits", 0),
            "misses":         info.get("keyspace_misses", 0),
            "hit_rate":       _calc_hit_rate(info),
            "memory_used":    memory.get("used_memory_human", "?"),
            "event_log_size": _redis.llen("volunteer:event_log"),
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@router.delete("/cache/flush")
def flush_cache(user: models.User = Depends(auth.organizer_required)):
    """5.2.3 Сброс всего кэша вручную (только организатор)."""
    if not REDIS_OK:
        return {"status": "Redis недоступен"}
    try:
        count = 0
        for pattern in ["volunteer:dashboard:*", "curator:dashboard:*", "tasks:list:*"]:
            for key in _redis.scan_iter(pattern):
                _redis.delete(key)
                count += 1
        return {"status": "OK", "flushed": count}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


def _calc_hit_rate(info: dict) -> str:
    hits   = info.get("keyspace_hits", 0)
    misses = info.get("keyspace_misses", 0)
    total  = hits + misses
    if total == 0:
        return "0%"
    return f"{hits / total * 100:.1f}%"

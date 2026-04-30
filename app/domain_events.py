"""
4.3 Event + Queue — Domain Events и обработка событий.

4.3.1 Domain Event — события публикуются из CQRS команд
Подписчик слушает Redis Pub/Sub и реагирует асинхронно.

Запускается как отдельный daemon-поток при старте FastAPI.
"""
import json
import threading
import logging
from datetime import datetime

logger = logging.getLogger("domain_events")

try:
    import redis as redis_lib
    _redis = redis_lib.Redis(host='localhost', port=6379, db=0, decode_responses=True)
    _redis.ping()
    REDIS_OK = True
except Exception:
    REDIS_OK = False


# ── Event Handlers ────────────────────────────────────────────────────────────

def on_application_created(payload: dict):
    """
    Реакция на ApplicationCreated:
    - Ставим задачу в очередь на отправку уведомления куратору
    """
    try:
        from task_queue import submit_task
        submit_task(
            "send_approval_notification",
            volunteer_id=payload.get("user_id"),
            task_title=payload.get("task_title", ""),
        )
        logger.info(f"[EVENT] ApplicationCreated → notification queued: {payload}")
    except Exception as e:
        logger.error(f"[EVENT] Handler error ApplicationCreated: {e}")


def on_application_approved(payload: dict):
    """
    Реакция на ApplicationApproved:
    4.3.3 Воркер обновляет Read Model через очередь:
    - Уведомление волонтёру → Redis Queue → Worker
    - Обновление кэша дашборда → Redis Queue → Worker
    """
    try:
        from task_queue import submit_task
        user_id = payload.get("user_id")

        # Уведомление в очередь
        submit_task(
            "send_approval_notification",
            volunteer_id=user_id,
            task_title=payload.get("task_id", ""),
        )

        # 4.3.3 Обновление Read Model через воркер (асинхронно)
        submit_task(
            "update_volunteer_read_model",
            user_id=user_id,
        )

        logger.info(
            f"[EVENT] ApplicationApproved → "
            f"notification + read_model update queued: user={user_id}"
        )
    except Exception as e:
        logger.error(f"[EVENT] Handler error ApplicationApproved: {e}")


def on_report_approved(payload: dict):
    """
    Реакция на ReportApproved (BR-09):
    4.3.3 Воркер обновляет Read Model:
    - Баллы начислены → кэш устарел → воркер пересчитывает
    """
    try:
        from task_queue import submit_task
        user_id = payload.get("user_id")
        points  = payload.get("points", 0)

        # 4.3.3 Обновление Read Model через воркер
        submit_task(
            "update_volunteer_read_model",
            user_id=user_id,
        )

        logger.info(
            f"[EVENT] ReportApproved → "
            f"read_model update queued: user={user_id} points={points}"
        )
    except Exception as e:
        logger.error(f"[EVENT] Handler error ReportApproved: {e}")


def on_report_rejected(payload: dict):
    """
    Реакция на ReportRejected.
    4.3.3 Обновляем Read Model — статус отчёта изменился.
    """
    try:
        from task_queue import submit_task
        user_id = payload.get("user_id")
        logger.info(
            f"[EVENT] ReportRejected: user={user_id} "
            f"reason={payload.get('reason')}"
        )
        # Обновляем кэш чтобы отклонённый отчёт исчез из pending
        submit_task("update_volunteer_read_model", user_id=user_id)
    except Exception as e:
        logger.error(f"[EVENT] Handler error ReportRejected: {e}")


# ── Event Router ──────────────────────────────────────────────────────────────

EVENT_HANDLERS = {
    "ApplicationCreated":  on_application_created,
    "ApplicationApproved": on_application_approved,
    "ApplicationRejected": lambda p: logger.info(f"[EVENT] ApplicationRejected: {p}"),
    "ReportApproved":      on_report_approved,
    "ReportRejected":      on_report_rejected,
}


class DomainEventSubscriber:
    """
    Подписчик на Domain Events через Redis Pub/Sub.
    Запускается в daemon-потоке при старте приложения.
    """
    def __init__(self):
        self._thread  = threading.Thread(target=self._run, daemon=True, name="EventSubscriber")
        self._running = False

    def start(self):
        if not REDIS_OK:
            logger.warning("[EVENTS] Redis недоступен, подписчик не запущен")
            return
        self._running = True
        self._thread.start()
        logger.info("[EVENTS] Domain Event subscriber started, channel=volunteer:events")

    def _run(self):
        try:
            r = redis_lib.Redis(host='localhost', port=6379, db=0, decode_responses=True)
            pubsub = r.pubsub()
            pubsub.subscribe("volunteer:events")

            for message in pubsub.listen():
                if not self._running:
                    break
                if message["type"] != "message":
                    continue

                try:
                    event = json.loads(message["data"])
                    event_type = event.get("type", "")
                    payload    = event.get("payload", {})

                    handler = EVENT_HANDLERS.get(event_type)
                    if handler:
                        handler(payload)
                    else:
                        logger.debug(f"[EVENTS] No handler for: {event_type}")

                except json.JSONDecodeError:
                    logger.error("[EVENTS] Bad JSON in event")
                except Exception as e:
                    logger.error(f"[EVENTS] Handler error: {e}")

        except Exception as e:
            logger.error(f"[EVENTS] Subscriber crashed: {e}")


# Глобальный подписчик — запускается из main.py
subscriber = DomainEventSubscriber()

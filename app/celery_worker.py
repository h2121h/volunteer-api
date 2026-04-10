import os
from dotenv import load_dotenv
from celery import Celery

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://default:LmfxjGzegWdQxQDBDuisdZGdwiETiqIp@interchange.proxy.rlwy.net:14241")

celery_app = Celery(
    "volunteer_tasks",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

celery_app.conf.broker_connection_retry_on_startup = True
celery_app.conf.broker_heartbeat = 10
celery_app.conf.broker_pool_limit = 1

@celery_app.task(name="send_notification", bind=True)
def send_notification_task(self, user_id: int, message: str):
    from app.logger import logger
    logger.info(f"[NOTIFICATION] user_id={user_id} message={message}")
    return {"status": "sent", "user_id": user_id}
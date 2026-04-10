from celery import Celery
from app.logger import logger

celery_app = Celery(
    "volunteer_tasks",
    broker="redis://default:LmfxjGzegWdQxQDBDuisdZGdwiETiqIp@interchange.proxy.rlwy.net:14241",
    backend="redis://default:LmfxjGzegWdQxQDBDuisdZGdwiETiqIp@interchange.proxy.rlwy.net:14241"
)

@celery_app.task
def send_notification_task(user_id: int, message: str):
    logger.info(f"[NOTIFICATION] user_id={user_id} message={message}")
    return {"status": "sent"}

celery_app.conf.broker_connection_retry_on_startup = True
celery_app.conf.broker_heartbeat = 10
celery_app.conf.broker_pool_limit = 1
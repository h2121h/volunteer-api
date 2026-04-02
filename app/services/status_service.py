from enum import Enum
from typing import List, Optional

class ApplicationStatus(str, Enum):
    CREATED = "created"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

ALLOWED_TRANSITIONS = {
    ApplicationStatus.CREATED: [ApplicationStatus.ACTIVE],
    ApplicationStatus.ACTIVE: [ApplicationStatus.COMPLETED, ApplicationStatus.CANCELLED],
    ApplicationStatus.COMPLETED: [],
    ApplicationStatus.CANCELLED: [],
}

FORBIDDEN_TRANSITIONS = {
    ApplicationStatus.COMPLETED: [ApplicationStatus.ACTIVE, ApplicationStatus.CREATED],
    ApplicationStatus.CANCELLED: [ApplicationStatus.ACTIVE, ApplicationStatus.CREATED],
}

def can_transition(current: ApplicationStatus, new: ApplicationStatus) -> bool:
    """Проверяет, разрешён ли переход из current в new"""
    return new in ALLOWED_TRANSITIONS.get(current, [])

def get_allowed_next_statuses(current: ApplicationStatus) -> List[ApplicationStatus]:
    """Возвращает список доступных следующих статусов"""
    return ALLOWED_TRANSITIONS.get(current, [])

def validate_transition(current: ApplicationStatus, new: ApplicationStatus) -> None:
    """Проверяет переход и возвращает ошибку если нельзя"""
    if not can_transition(current, new):
        raise ValueError(f"Недопустимый переход из {current.value} в {new.value}")
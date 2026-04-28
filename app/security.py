"""
6. Безопасность — по конспекту:
  - SQL инъекции    → SQLAlchemy ORM (параметризованные запросы)
  - Rate Limiting   → slowapi (защита от перебора)
  - CORS            → только свои домены
  - XSS             → валидация + экранирование входных данных
  - Mass Assignment → Pydantic DTO (только разрешённые поля)
  - Валидация       → типы, диапазоны, формат, обязательность
"""
import re
import html
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator


# ── 1. ЗАЩИТА ОТ XSS — экранирование и валидация ─────────────────────────────

def sanitize_string(value: str) -> str:
    """
    XSS защита: экранируем HTML символы.
    < > & " ' → &lt; &gt; &amp; &quot; &#x27;
    """
    if not value:
        return value
    # Убираем потенциально опасные теги
    value = html.escape(value, quote=True)
    # Убираем скрипты даже если обёрнуты
    value = re.sub(r'<script.*?>.*?</script>', '', value, flags=re.DOTALL | re.IGNORECASE)
    value = re.sub(r'javascript:', '', value, flags=re.IGNORECASE)
    value = re.sub(r'on\w+\s*=', '', value, flags=re.IGNORECASE)
    return value.strip()


def validate_email_format(email: str) -> bool:
    """Валидация формата email."""
    pattern = r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


# ── 2. PYDANTIC DTO — защита от Mass Assignment ───────────────────────────────
# Указываем ТОЛЬКО разрешённые поля — лишние игнорируются

class RegisterDTO(BaseModel):
    """
    Mass Assignment защита: только эти поля принимаем от пользователя.
    Нельзя передать role_id, is_active, is_admin напрямую.
    """
    name:     str     = Field(..., min_length=2,  max_length=120)
    email:    str     = Field(..., min_length=5,  max_length=180)
    password: str     = Field(..., min_length=8,  max_length=100)
    phone:    Optional[str] = Field(None, max_length=30)
    city:     Optional[str] = Field(None, max_length=100)
    role:     str     = Field("volunteer", pattern=r'^(volunteer|organizer|curator)$')

    @field_validator('name')
    @classmethod
    def validate_name(cls, v):
        v = sanitize_string(v)
        if not re.match(r'^[a-zA-Zа-яА-ЯёЁ\s\-]{2,120}$', v):
            raise ValueError('Имя содержит недопустимые символы')
        return v

    @field_validator('email')
    @classmethod
    def validate_email(cls, v):
        v = v.strip().lower()
        if not validate_email_format(v):
            raise ValueError('Неверный формат email')
        return v

    @field_validator('password')
    @classmethod
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('Пароль должен быть не менее 8 символов')
        if not re.search(r'[A-Za-zА-Яа-я]', v):
            raise ValueError('Пароль должен содержать буквы')
        if not re.search(r'[0-9]', v):
            raise ValueError('Пароль должен содержать цифры')
        return v

    @field_validator('city', 'phone', mode='before')
    @classmethod
    def sanitize_optional(cls, v):
        if v:
            return sanitize_string(str(v))
        return v

    class Config:
        # extra='forbid' — запрещаем лишние поля (Mass Assignment)
        extra = 'ignore'


class LoginDTO(BaseModel):
    email:    str = Field(..., min_length=5, max_length=180)
    password: str = Field(..., min_length=1, max_length=100)

    @field_validator('email')
    @classmethod
    def validate_email(cls, v):
        return v.strip().lower()

    class Config:
        extra = 'ignore'


class CreateProjectDTO(BaseModel):
    """Только разрешённые поля — нельзя передать created_by, status напрямую."""
    title:       str           = Field(..., min_length=3, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)

    @field_validator('title', 'description', mode='before')
    @classmethod
    def sanitize(cls, v):
        return sanitize_string(str(v)) if v else v

    class Config:
        extra = 'ignore'


class CreateTaskDTO(BaseModel):
    """Только разрешённые поля — нельзя передать status напрямую."""
    project_id:    int            = Field(..., gt=0)
    title:         str            = Field(..., min_length=3, max_length=180)
    description:   Optional[str]  = Field(None, max_length=2000)
    event_date:    str            = Field(..., pattern=r'^\d{4}-\d{2}-\d{2}$')
    location:      Optional[str]  = Field(None, max_length=150)
    needed_people: int            = Field(5, ge=1, le=1000)
    difficulty:    str            = Field("medium", pattern=r'^(easy|medium|hard)$')
    category:      str            = Field("other",
                                    pattern=r'^(ecology|children|elderly|animals|other)$')
    lat:           Optional[float] = Field(None, ge=-90,  le=90)
    lng:           Optional[float] = Field(None, ge=-180, le=180)

    @field_validator('title', 'description', 'location', mode='before')
    @classmethod
    def sanitize(cls, v):
        return sanitize_string(str(v)) if v else v

    @field_validator('event_date')
    @classmethod
    def validate_date(cls, v):
        from datetime import date
        try:
            d = date.fromisoformat(v)
            if d < date.today():
                raise ValueError('Дата события не может быть в прошлом')
        except ValueError as e:
            raise ValueError(f'Неверный формат даты: {e}')
        return v

    class Config:
        extra = 'ignore'


class ApplyTaskDTO(BaseModel):
    message: Optional[str] = Field("Хочу помочь!", max_length=500)

    @field_validator('message', mode='before')
    @classmethod
    def sanitize(cls, v):
        return sanitize_string(str(v)) if v else v

    class Config:
        extra = 'ignore'


class SubmitReportDTO(BaseModel):
    task_id: int   = Field(..., gt=0)
    hours:   float = Field(..., ge=0.5, le=24.0)
    comment: str   = Field(..., min_length=10, max_length=2000)

    @field_validator('comment', mode='before')
    @classmethod
    def sanitize(cls, v):
        return sanitize_string(str(v)) if v else v

    class Config:
        extra = 'ignore'

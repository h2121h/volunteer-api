from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime


# Пользователи
class UserBase(BaseModel):
    email: EmailStr
    username: str
    full_name: Optional[str] = None


class UserCreate(UserBase):
    password: str = Field(..., min_length=4)
    role_id: Optional[int] = None


class UserLogin(BaseModel):
    username: str
    password: str


class UserResponse(UserBase):
    id: int
    role_id: Optional[int]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None


# Задачи
class TaskBase(BaseModel):
    title: str
    description: Optional[str] = None
    project_id: Optional[int] = None
    location: Optional[str] = None
    required_skills: Optional[str] = None
    status: str = "open"
    priority: str = "medium"
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


class TaskCreate(TaskBase):
    pass


class TaskResponse(TaskBase):
    id: int
    created_by: int
    created_at: datetime

    class Config:
        from_attributes = True


# Отчеты
class ReportBase(BaseModel):
    task_id: int
    content: str
    hours_spent: float
    photos: Optional[str] = None


class ReportCreate(ReportBase):
    pass


class ReportResponse(ReportBase):
    id: int
    user_id: int
    status: str
    submitted_at: datetime

    class Config:
        from_attributes = True
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime, date


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    email: Optional[str] = None


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=4)
    name: str
    role: str = "volunteer"
    phone: Optional[str] = None
    city: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: int
    email: EmailStr
    name: str
    role_id: Optional[int]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class TaskCreate(BaseModel):
    project_id: int
    title: str
    description: Optional[str] = None
    event_date: date
    location: Optional[str] = None
    needed_people: int = 5


class TaskResponse(BaseModel):
    id: int
    project_id: int
    title: str
    description: Optional[str]
    event_date: date
    location: Optional[str]
    needed_people: int
    status: str

    class Config:
        from_attributes = True


class ReportCreate(BaseModel):
    task_id: int
    comment: str
    hours: float
    photo_url: Optional[str] = None


class ReportResponse(BaseModel):
    id: int
    assignment_id: int
    user_id: int
    comment: Optional[str]
    hours: Optional[float]
    is_approved: bool
    submitted_at: datetime

    class Config:
        from_attributes = True
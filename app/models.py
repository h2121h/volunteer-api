from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Float, Table
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

user_skills = Table(
    'user_skills',
    Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id')),
    Column('skill_id', Integer, ForeignKey('skills.id'))
)

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    role_id = Column(Integer, ForeignKey('roles.id'))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    role = relationship("Role", back_populates="users")
    skills = relationship("Skill", secondary=user_skills, back_populates="users")
    tasks_created = relationship("Task", foreign_keys="Task.created_by", back_populates="creator")
    task_applications = relationship("TaskApplication", foreign_keys="TaskApplication.user_id", back_populates="user")
    task_assignments = relationship("TaskAssignment", foreign_keys="TaskAssignment.user_id", back_populates="user")
    reports = relationship("TaskReport", foreign_keys="TaskReport.user_id", back_populates="user")
    documents = relationship("VolunteerDocument", foreign_keys="VolunteerDocument.user_id", back_populates="user")

class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, nullable=False)
    name = Column(String, unique=True, nullable=False)

    users = relationship("User", back_populates="role")

class Skill(Base):
    __tablename__ = "skills"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    category = Column(String)

    users = relationship("User", secondary=user_skills, back_populates="users")

class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text)
    start_date = Column(DateTime)
    end_date = Column(DateTime)
    status = Column(String, default="active")
    created_by = Column(Integer, ForeignKey('users.id'))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    creator = relationship("User", foreign_keys=[created_by])
    tasks = relationship("Task", back_populates="project")

class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text)
    project_id = Column(Integer, ForeignKey('projects.id'))
    location = Column(String)
    required_skills = Column(String)
    status = Column(String, default="open")
    priority = Column(String, default="medium")
    start_date = Column(DateTime)
    end_date = Column(DateTime)
    created_by = Column(Integer, ForeignKey('users.id'))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    project = relationship("Project", back_populates="tasks")
    creator = relationship("User", foreign_keys=[created_by], back_populates="tasks_created")
    applications = relationship("TaskApplication", foreign_keys="TaskApplication.task_id", back_populates="task")
    assignments = relationship("TaskAssignment", foreign_keys="TaskAssignment.task_id", back_populates="task")
    reports = relationship("TaskReport", foreign_keys="TaskReport.task_id", back_populates="task")

class TaskApplication(Base):
    __tablename__ = "task_applications"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey('tasks.id'))
    user_id = Column(Integer, ForeignKey('users.id'))
    status = Column(String, default="pending")
    message = Column(Text)
    applied_at = Column(DateTime(timezone=True), server_default=func.now())

    task = relationship("Task", foreign_keys=[task_id], back_populates="applications")
    user = relationship("User", foreign_keys=[user_id], back_populates="task_applications")

class TaskAssignment(Base):
    __tablename__ = "task_assignments"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey('tasks.id'))
    user_id = Column(Integer, ForeignKey('users.id'))
    assigned_by = Column(Integer, ForeignKey('users.id'))
    assigned_at = Column(DateTime(timezone=True), server_default=func.now())
    status = Column(String, default="assigned")

    task = relationship("Task", foreign_keys=[task_id], back_populates="assignments")
    user = relationship("User", foreign_keys=[user_id], back_populates="task_assignments")
    assigner = relationship("User", foreign_keys=[assigned_by])

class TaskReport(Base):
    __tablename__ = "task_reports"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey('tasks.id'))
    user_id = Column(Integer, ForeignKey('users.id'))
    content = Column(Text, nullable=False)
    hours_spent = Column(Float)
    photos = Column(String)
    status = Column(String, default="submitted")
    submitted_at = Column(DateTime(timezone=True), server_default=func.now())
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_by = Column(Integer, ForeignKey('users.id'), nullable=True)

    task = relationship("Task", foreign_keys=[task_id], back_populates="reports")
    user = relationship("User", foreign_keys=[user_id], back_populates="reports")
    reviewer = relationship("User", foreign_keys=[reviewed_by])

class VolunteerDocument(Base):
    __tablename__ = "volunteer_documents"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    document_type = Column(String)
    file_path = Column(String)
    verified = Column(Boolean, default=False)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())
    verified_at = Column(DateTime(timezone=True), nullable=True)
    verified_by = Column(Integer, ForeignKey('users.id'), nullable=True)

    user = relationship("User", foreign_keys=[user_id], back_populates="documents")
    verifier = relationship("User", foreign_keys=[verified_by])

class ProjectFeedback(Base):
    __tablename__ = "project_feedback"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey('projects.id'))
    user_id = Column(Integer, ForeignKey('users.id'))
    rating = Column(Integer)
    comment = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    project = relationship("Project")
    user = relationship("User")
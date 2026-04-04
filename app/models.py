from sqlalchemy import (
    Column, SmallInteger, Integer, BigInteger, String, Boolean,
    DateTime, Date, ForeignKey, Text, Numeric, UniqueConstraint, Index, Table
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import INET
from app.database import Base


user_skills = Table(
    'user_skills',
    Base.metadata,
    Column('user_id',  BigInteger,   ForeignKey('users.id',  ondelete='CASCADE')),
    Column('skill_id', SmallInteger, ForeignKey('skills.id', ondelete='CASCADE')),
)


class Role(Base):
    __tablename__ = 'roles'

    id   = Column(SmallInteger, primary_key=True, autoincrement=True)
    code = Column(String(30),  unique=True, nullable=False)
    name = Column(String(100), nullable=False)

    users = relationship('User', back_populates='role')


class User(Base):
    __tablename__ = 'users'

    id            = Column(BigInteger, primary_key=True, autoincrement=True)
    email         = Column(String(180), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    name          = Column(String(120), nullable=False)
    phone         = Column(String(30))
    city          = Column(String(100))
    role_id       = Column(SmallInteger, ForeignKey('roles.id'))
    is_active     = Column(Boolean, default=True)
    is_verified   = Column(Boolean, default=False)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())
    last_login_at = Column(DateTime(timezone=True))

    role              = relationship('Role', back_populates='users')
    skills            = relationship('Skill', secondary=user_skills, back_populates='users')
    documents         = relationship('VolunteerDocument',
                                     foreign_keys='VolunteerDocument.user_id',
                                     back_populates='user')
    projects_created  = relationship('Project',
                                     foreign_keys='Project.created_by',
                                     back_populates='creator')
    task_applications = relationship('TaskApplication',
                                     foreign_keys='TaskApplication.user_id',
                                     back_populates='user')
    task_assignments  = relationship('TaskAssignment',
                                     foreign_keys='TaskAssignment.user_id',
                                     back_populates='user')
    reports           = relationship('TaskReport',
                                     foreign_keys='TaskReport.user_id',
                                     back_populates='user')
    feedback          = relationship('ProjectFeedback',
                                     foreign_keys='ProjectFeedback.user_id',
                                     back_populates='user')


class Login(Base):
    __tablename__ = 'logins'

    id          = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id     = Column(BigInteger, ForeignKey('users.id', ondelete='SET NULL'))
    email       = Column(String(180))
    ip          = Column(INET)
    user_agent  = Column(Text)
    success     = Column(Boolean, nullable=False)
    reason      = Column(String(80))
    happened_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship('User')

    __table_args__ = (
        Index('idx_logins_email', 'email', 'happened_at'),
    )


class VolunteerDocument(Base):
    __tablename__ = 'volunteer_documents'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey('users.id', ondelete='CASCADE'))
    doc_type = Column(String(80), nullable=False)
    file_url = Column(Text, nullable=False)
    status = Column(String(20), default='new')
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())
    verified_at = Column(DateTime(timezone=True))
    verified_by = Column(BigInteger, ForeignKey('users.id'))

    user = relationship('User', foreign_keys=[user_id], back_populates='documents')
    verifier = relationship('User', foreign_keys=[verified_by])


class Project(Base):
    __tablename__ = 'projects'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False)
    description = Column(Text)
    status = Column(String(20), default='active')
    created_by = Column(BigInteger, ForeignKey('users.id'))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    creator = relationship('User', foreign_keys=[created_by], back_populates='projects_created')
    tasks = relationship('Task', back_populates='project')
    feedback = relationship('ProjectFeedback', back_populates='project')


class Task(Base):
    __tablename__ = 'tasks'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(BigInteger, ForeignKey('projects.id', ondelete='CASCADE'))
    title = Column(String(180), nullable=False)
    description = Column(Text)
    event_date = Column(Date, nullable=False)
    location = Column(String(150))
    needed_people = Column(SmallInteger, default=5)
    status = Column(String(20), default='open')

    project = relationship('Project', back_populates='tasks')
    applications = relationship('TaskApplication',
                                foreign_keys='TaskApplication.task_id',
                                back_populates='task')
    assignments = relationship('TaskAssignment',
                               foreign_keys='TaskAssignment.task_id',
                               back_populates='task')

    __table_args__ = (
        Index('idx_tasks_date', 'event_date'),
    )


class TaskApplication(Base):
    __tablename__ = 'task_applications'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    task_id = Column(BigInteger, ForeignKey('tasks.id', ondelete='CASCADE'))
    user_id = Column(BigInteger, ForeignKey('users.id', ondelete='CASCADE'))
    status = Column(String(20), default='pending')
    message = Column(Text)
    applied_at = Column(DateTime(timezone=True), server_default=func.now())

    task = relationship('Task', foreign_keys=[task_id], back_populates='applications')
    user = relationship('User', foreign_keys=[user_id], back_populates='task_applications')

    __table_args__ = (
        UniqueConstraint('task_id', 'user_id'),
        Index('idx_applications_task', 'task_id', 'status'),
    )


class TaskAssignment(Base):
    __tablename__ = 'task_assignments'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    task_id = Column(BigInteger, ForeignKey('tasks.id', ondelete='CASCADE'))
    user_id = Column(BigInteger, ForeignKey('users.id', ondelete='CASCADE'))
    assigned_at = Column(DateTime(timezone=True), server_default=func.now())
    assigned_by = Column(BigInteger, ForeignKey('users.id'))
    status = Column(String(20), default='assigned')

    task = relationship('Task', foreign_keys=[task_id], back_populates='assignments')
    user = relationship('User', foreign_keys=[user_id], back_populates='task_assignments')
    assigner = relationship('User', foreign_keys=[assigned_by])
    reports = relationship('TaskReport', back_populates='assignment')

    __table_args__ = (
        Index('idx_assignments_task', 'task_id'),
    )


class TaskReport(Base):
    __tablename__ = 'task_reports'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    assignment_id = Column(BigInteger,
                           ForeignKey('task_assignments.id', ondelete='CASCADE'))
    user_id = Column(BigInteger, ForeignKey('users.id'))
    hours = Column(Numeric(5, 2))
    comment = Column(Text)
    photo_url = Column(Text)
    submitted_at = Column(DateTime(timezone=True), server_default=func.now())
    is_approved = Column(Boolean, default=False)

    assignment = relationship('TaskAssignment', back_populates='reports')
    user = relationship('User', foreign_keys=[user_id], back_populates='reports')

    __table_args__ = (
        Index('idx_reports_assignment', 'assignment_id'),
    )


class ProjectFeedback(Base):
    __tablename__ = 'project_feedback'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(BigInteger, ForeignKey('projects.id', ondelete='CASCADE'))
    user_id = Column(BigInteger, ForeignKey('users.id'))
    rating = Column(SmallInteger)
    comment = Column(Text)
    submitted_at = Column(DateTime(timezone=True), server_default=func.now())

    project = relationship('Project', back_populates='feedback')
    user = relationship('User', foreign_keys=[user_id], back_populates='feedback')


class Skill(Base):
    __tablename__ = 'skills'

    id = Column(SmallInteger, primary_key=True, autoincrement=True)
    name = Column(String(80), unique=True, nullable=False)

    users = relationship('User', secondary=user_skills, back_populates='skills')
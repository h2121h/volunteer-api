from sqlalchemy import (
    Column, SmallInteger, Integer, BigInteger, String, Boolean,
    DateTime, Date, ForeignKey, Text, Numeric, UniqueConstraint, Index, Table
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import INET
from app.database import Base


# ─── Many-to-many: user_skills ───────────────────────────────────────────────

user_skills = Table(
    'user_skills',
    Base.metadata,
    Column('user_id',  BigInteger,   ForeignKey('users.id',  ondelete='CASCADE')),
    Column('skill_id', SmallInteger, ForeignKey('skills.id', ondelete='CASCADE')),
)


# ─── Role ────────────────────────────────────────────────────────────────────

class Role(Base):
    __tablename__ = 'roles'

    id   = Column(SmallInteger, primary_key=True, autoincrement=True)
    code = Column(String(30),  unique=True, nullable=False)
    name = Column(String(100), nullable=False)

    users = relationship('User', back_populates='role')


# ─── User ────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = 'users'

    id            = Column(BigInteger, primary_key=True, autoincrement=True)
    email         = Column(String(180), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    name          = Column(String(120), nullable=False)   # full_name -> name
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
    backups_performed = relationship('Backup',
                                     foreign_keys='Backup.performed_by',
                                     back_populates='performer')


# ─── Login log ───────────────────────────────────────────────────────────────

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

    table_args = (
        Index('idx_logins_email', 'email', 'happened_at'),
    )


# ─── Volunteer documents ─────────────────────────────────────────────────────

class VolunteerDocument(Base):
    __tablename__ = 'volunteer_documents'
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey('users.id', ondelete='CASCADE'))
    doc_type = Column(String(80), nullable=False)  # document_type -> doc_type
    file_url = Column(Text, nullable=False)  # file_path -> file_url
    status = Column(String(20), default='new')  # verified bool -> status varchar
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())
    verified_at = Column(DateTime(timezone=True))
    verified_by = Column(BigInteger, ForeignKey('users.id'))

    user = relationship('User', foreign_keys=[user_id], back_populates='documents')
    verifier = relationship('User', foreign_keys=[verified_by])


# ─── Project ─────────────────────────────────────────────────────────────────

class Project(Base):
    __tablename__ = 'projects'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False)  # name -> title
    description = Column(Text)
    status = Column(String(20), default='active')
    created_by = Column(BigInteger, ForeignKey('users.id'))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # start_date / end_date отсутствуют в SQL-схеме — убраны

    creator = relationship('User', foreign_keys=[created_by], back_populates='projects_created')
    tasks = relationship('Task', back_populates='project')
    feedback = relationship('ProjectFeedback', back_populates='project')


# ─── Task ────────────────────────────────────────────────────────────────────

class Task(Base):
    __tablename__ = 'tasks'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(BigInteger, ForeignKey('projects.id', ondelete='CASCADE'))
    title = Column(String(180), nullable=False)
    description = Column(Text)
    event_date = Column(Date, nullable=False)  # start/end_date -> event_date
    location = Column(String(150))
    needed_people = Column(SmallInteger, default=5)  # добавлено из SQL
    status = Column(String(20), default='open')
    # priority, required_skills, created_by отсутствуют в SQL-схеме — убраны

    project = relationship('Project', back_populates='tasks')
    applications = relationship('TaskApplication',
                                foreign_keys='TaskApplication.task_id',
                                back_populates='task')
    assignments = relationship('TaskAssignment',
                               foreign_keys='TaskAssignment.task_id',
                               back_populates='task')

    table_args = (
        Index('idx_tasks_date', 'event_date'),
    )


# ─── Task application ────────────────────────────────────────────────────────

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

    table_args = (
        UniqueConstraint('task_id', 'user_id'),
        Index('idx_applications_task', 'task_id', 'status'),
    )


# ─── Task assignment ─────────────────────────────────────────────────────────

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

    table_args = (
        Index('idx_assignments_task', 'task_id'),
    )


# ─── Task report ─────────────────────────────────────────────────────────────

class TaskReport(Base):
    __tablename__ = 'task_reports'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    assignment_id = Column(BigInteger,
                           ForeignKey('task_assignments.id', ondelete='CASCADE'))
    user_id = Column(BigInteger, ForeignKey('users.id'))
    hours = Column(Numeric(5, 2))  # hours_spent -> hours
    comment = Column(Text)  # content -> comment
    photo_url = Column(Text)  # photos -> photo_url
    submitted_at = Column(DateTime(timezone=True), server_default=func.now())
    is_approved = Column(Boolean, default=False)  # status/reviewed_* -> is_approved

    assignment = relationship('TaskAssignment', back_populates='reports')
    user = relationship('User', foreign_keys=[user_id], back_populates='reports')

    table_args = (
        Index('idx_reports_assignment', 'assignment_id'),
    )


# ─── Project feedback ────────────────────────────────────────────────────────

class ProjectFeedback(Base):
    __tablename__ = 'project_feedback'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(BigInteger, ForeignKey('projects.id', ondelete='CASCADE'))
    user_id = Column(BigInteger, ForeignKey('users.id'))
    rating = Column(SmallInteger)  # CHECK (1..5) задан на уровне БД
    comment = Column(Text)
    submitted_at = Column(DateTime(timezone=True), server_default=func.now())  # created_at -> submitted_at

    project = relationship('Project', back_populates='feedback')
    user = relationship('User', foreign_keys=[user_id], back_populates='feedback')


# ─── Skill ───────────────────────────────────────────────────────────────────

class Skill(Base):
    __tablename__ = 'skills'

    id = Column(SmallInteger, primary_key=True, autoincrement=True)
    name = Column(String(80), unique=True, nullable=False)
    # category отсутствует в SQL-схеме — убрано

    users = relationship('User', secondary=user_skills, back_populates='skills')


# ─── Backup ──────────────────────────────────────────────────────────────────

class Backup(Base):
    __tablename__ = 'backups'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    performed_by = Column(BigInteger, ForeignKey('users.id'))
    backup_date = Column(DateTime(timezone=True), server_default=func.now())
    file_path = Column(Text)
    size_mb = Column(Integer)
    status = Column(String(20), default='success')

    performer = relationship('User', foreign_keys=[performed_by], back_populates='backups_performed')


# ─── Registration ────────────────────────────────────────────────────────────

class Registration(Base):
    __tablename__ = 'registration'

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    email = Column(String(180), unique=True, nullable=False)
    token = Column(String(100))
    status = Column(String(20), default='new')
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    user_id = Column(BigInteger)  # намеренно без FK — соответствует SQL

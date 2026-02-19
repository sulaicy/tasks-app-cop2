# models.py
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, Date, ForeignKey
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

Base = declarative_base()


class Group(Base):
    __tablename__ = 'groups'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    users = relationship('User', back_populates='group')
    tasks = relationship('Task', back_populates='assigned_group')


class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    email = Column(String(150), nullable=False, unique=True)
    password_hash = Column(String(256), nullable=False)
    role = Column(String(20), default='user')  # 'admin' or 'user'
    group_id = Column(Integer, ForeignKey('groups.id'), nullable=True)
    group = relationship('Group', back_populates='users')


class Task(Base):
    __tablename__ = 'tasks'
    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    description = Column(String(500), nullable=True)
    is_global = Column(Boolean, default=False)
    assigned_to = Column(Integer, ForeignKey('users.id'), nullable=True)
    assigned_group_id = Column(Integer, ForeignKey('groups.id'), nullable=True)
    points_per_unit = Column(Float, default=1.0)
    unit_name = Column(String(50), nullable=True)
    created_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    assigned_group = relationship('Group', back_populates='tasks')
    instances = relationship('TaskInstance', back_populates='task')


class TaskInstance(Base):
    __tablename__ = 'task_instances'
    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey('tasks.id'), nullable=False)
    date = Column(Date, nullable=False)
    target_value = Column(Float, default=0.0)
    completed_value = Column(Float, nullable=True)
    completed_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    status = Column(String(20), default='pending')  # 'pending' or 'done'
    points_awarded = Column(Float, nullable=True)
    task = relationship('Task', back_populates='instances')


def get_engine(db_url: str):
    return create_engine(db_url, connect_args={"check_same_thread": False} if "sqlite" in db_url else {})


def get_session(engine):
    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    return Session()

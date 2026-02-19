# streamlit_app.py
import os
import streamlit as st
from datetime import date, datetime
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import (
    Column, Integer, String, Boolean, Date, DateTime, Float,
    ForeignKey, create_engine
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
import pandas as pd
import plotly.express as px

# -------------------------
# Configuration and DB init
# -------------------------
# Read configuration from environment (Streamlit Secrets are exposed as env vars)
DB_URL = os.getenv("DATABASE_URL", "sqlite:///task_tracker.db")
# Default admin credentials (created automatically if no admin exists)
DEFAULT_ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@example.com")
DEFAULT_ADMIN_PASS = os.getenv("ADMIN_PASS", "admin123")

Base = declarative_base()

def get_engine(db_url):
    connect_args = {}
    if db_url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
    return create_engine(db_url, connect_args=connect_args)

engine = get_engine(DB_URL)
SessionLocal = sessionmaker(bind=engine)
session = SessionLocal()

# -------------------------
# Models
# -------------------------
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    email = Column(String(150), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), default="user")
    created_at = Column(DateTime, default=datetime.utcnow)

class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False)
    description = Column(String, nullable=True)
    points_per_unit = Column(Float, default=1.0)
    unit_name = Column(String(50), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class TaskInstance(Base):
    __tablename__ = "task_instances"
    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    date = Column(Date, nullable=False)
    target_value = Column(Float, default=0.0)
    completed_value = Column(Float, default=0.0)
    completed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    status = Column(String(20), default="pending")
    points_awarded = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)

# Create tables if they don't exist
Base.metadata.create_all(engine)

# -------------------------
# Helper functions
# -------------------------
def get_user_by_email(email):
    return session.query(User).filter_by(email=email).first()

def create_user(name, email, password, role="user"):
    if get_user_by_email(email):
        return None
    u = User(name=name, email=email, password_hash=generate_password_hash(password), role=role)
    session.add(u)
    session.commit()
    return u

def verify_password(user, password):
    return check_password_hash(user.password_hash, password)

def compute_points(completed_value, points_per_unit):
    return (completed_value or 0.0) * (points_per_unit or 1.0)

# Create default admin if none exists
if not session.query(User).filter_by(role="admin").first():
    if not get_user_by_email(DEFAULT_ADMIN_EMAIL):
        create_user("Admin", DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASS, role="admin")

# -------------------------
# Streamlit UI
# -------------------------
st.set_page_config(page_title="Task Tracker", layout="wide")
st.title("Task Tracker")

# Session state for simple auth
if "user_id" not in st.session_state:
    st.session_state["user_id"] = None
    st.session_state["user_name"] = None
    st.session_state["user_role"] = None

def login_flow():
    st.header("تسجيل الدخول")
    with st.form("login_form"):
        email = st.text_input("البريد الإلكتروني")
        password = st.text_input("كلمة المرور", type="password")
        submitted = st.form_submit_button("دخول")
    if submitted:
        user = get_user_by_email(email.strip())
        if not user:
            st.error("المستخدم غير موجود")
            return
        if verify_password(user, password):
            st.session_state["user_id"] = user.id
            st.session_state["user_name"] = user.name
            st.session_state["user_role"] = user.role
            st.success(f"مرحباً، {user.name}")
        else:
            st.error("كلمة المرور غير صحيحة")

def logout():
    st.session_state["user_id"] = None
    st.session_state["user_name"] = None
    st.session_state["user_role"] = None
    st.experimental_rerun()

# If not logged in, show login
if not st.session_state.get("user_id"):
    login_flow()
else:
    # Authenticated UI
    user = session.query(User).get(st.session_state["user_id"])
    st.sidebar.write(f"**{user.name}** — {user.role}")
    if st.sidebar.button("تسجيل خروج"):
        logout()

    menu = st.sidebar.radio("القائمة", ["Dashboard", "مهام اليوم", "المهام", "المستخدمون" if user.role == "admin" else ""])

    if menu == "Dashboard":
        st.header("لوحة التقدم")
        today = date.today()
        q = session.query(TaskInstance).filter_by(date=today).all()
        rows = []
        for i in q:
            u = session.query(User).get(i.completed_by) if i.completed_by else None
            t = session.query(Task).get(i.task_id)
            rows.append({"user": u.name if u else "غير مكتمل", "task": t.title if t else f"#{i.task_id}", "points": i.points_awarded or 0})
        df = pd.DataFrame(rows)
        if df.empty:
            st.info("لا توجد بيانات لليوم")
        else:
            agg = df.groupby("user", as_index=False).sum()
            fig = px.bar(agg, x="user", y="points", title="نقاط كل مستخدم اليوم")
            st.plotly_chart(fig, use_container_width=True)

    elif menu == "مهام اليوم":
        st.header("مهام اليوم")
        today = date.today()
        instances = session.query(TaskInstance).filter_by(date=today).all()
        if not instances:
            st.info("لا توجد مثيلات لليوم. يمكنك إنشاء مثيل من صفحة 'المهام'.")
        for inst in instances:
            t = session.query(Task).get(inst.task_id)
            st.subheader(t.title if t else f"مهمة #{inst.task_id}")
            st.write(t.description if t and t.description else "")
            col1, col2 = st.columns([2,1])
            with col1:
                st.write(f"الهدف: {inst.target_value} {t.unit_name if t else ''}")
                val = st.number_input("قيمة الإنجاز", value=float(inst.completed_value or 0.0), key=f"val_{inst.id}")
            with col2:
                if st.button("تسجيل إنجاز", key=f"btn_{inst.id}"):
                    points = compute_points(val, t.points_per_unit if t else 1.0)
                    inst.completed_value = val
                    inst.completed_by = user.id
                    inst.status = "done"
                    inst.points_awarded = points
                    session.commit()
                    st.success(f"تم تسجيل {points} نقطة")
                    st.experimental_rerun()

    elif menu == "المهام":
        st.header("إدارة المهام")
        st.subheader("إنشاء مهمة جديدة")
        with st.form("create_task"):
            title = st.text_input("عنوان المهمة")
            desc = st.text_area("وصف")
            points_per_unit = st.number_input("نقاط لكل وحدة", value=1.0)
            unit_name = st.text_input("اسم الوحدة")
            submitted = st.form_submit_button("إنشاء")
        if submitted:
            t = Task(title=title, description=desc, points_per_unit=points_per_unit, unit_name=unit_name, created_by=user.id)
            session.add(t); session.commit()
            st.success("تم إنشاء المهمة")

        st.subheader("قائمة المهام")
        tasks = session.query(Task).all()
        for t in tasks:
            st.write(f"- **{t.title}** — {t.unit_name or ''} — نقاط/وحدة: {t.points_per_unit}")

        st.subheader("إنشاء مثيل مهمة لليوم")
        task_options = session.query(Task).all()
        sel = st.selectbox("اختر مهمة", options=[None]+[t.id for t in task_options], format_func=lambda x: "—" if x is None else session.query(Task).get(x).title)
        if sel:
            if st.button("إنشاء مثيل لليوم"):
                today = date.today()
                exists = session.query(TaskInstance).filter_by(task_id=sel, date=today).first()
                if exists:
                    st.warning("موجود بالفعل لليوم")
                else:
                    ti = TaskInstance(task_id=sel, date=today, target_value=0.0)
                    session.add(ti); session.commit()
                    st.success("تم الإنشاء")
                    st.experimental_rerun()

    elif menu == "المستخدمون" and user.role == "admin":
        st.header("إدارة المستخدمين")
        st.subheader("إنشاء مستخدم جديد")
        with st.form("create_user"):
            uname = st.text_input("الاسم")
            uemail = st.text_input("البريد الإلكتروني")
            upass = st.text_input("كلمة المرور", type="password")
            if st.form_submit_button("إنشاء مستخدم"):
                if get_user_by_email(uemail):
                    st.error("البريد موجود")
                else:
                    create_user(uname, uemail, upass, role="user")
                    st.success("تم إنشاء المستخدم")

        st.subheader("قائمة المستخدمين")
        users = session.query(User).all()
        for u in users:
            st.write(f"- {u.name} ({u.email}) — {u.role}")

# End of file

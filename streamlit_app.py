# streamlit_app.py
import streamlit as st
import os
from dotenv import load_dotenv
from models import get_engine, get_session, User, Group, Task, TaskInstance
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date
import pandas as pd
import plotly.express as px

load_dotenv()
DB_URL = os.getenv('DATABASE_URL', 'sqlite:///task_tracker.db')

# ✅ إصلاح: استخدام cache_resource لتجنب إعادة إنشاء الجلسة في كل تحديث
@st.cache_resource
def init_db():
    engine = get_engine(DB_URL)
    return get_session(engine)

session = init_db()

st.set_page_config(page_title="متتبع المهام", layout="wide", initial_sidebar_state="expanded")

# --- مساعدات ---
def get_user_by_email(email: str):
    return session.query(User).filter_by(email=email).first()

def create_admin_if_none():
    admin = session.query(User).filter_by(role='admin').first()
    if not admin:
        if not get_user_by_email('admin@example.com'):
            u = User(
                name='Admin',
                email='admin@example.com',
                password_hash=generate_password_hash('admin123'),
                role='admin'
            )
            session.add(u)
            session.commit()
            st.info("تم إنشاء المدير: admin@example.com / admin123")

def login(email: str, password: str):
    u = get_user_by_email(email)
    if u and check_password_hash(u.password_hash, password):
        return u
    return None

def compute_points(completed_value: float, points_per_unit: float) -> float:
    return completed_value * (points_per_unit or 1.0)

def get_user(user_id: int):
    # ✅ إصلاح: session.get() بدلاً من session.query().get() المهملة في SQLAlchemy 2.0
    return session.get(User, user_id)

def get_task(task_id: int):
    return session.get(Task, task_id)

def get_group(group_id: int):
    return session.get(Group, group_id)

# --- تهيئة ---
create_admin_if_none()

if 'page' not in st.session_state:
    st.session_state['page'] = 'login'

# ===================== صفحة تسجيل الدخول =====================
if st.session_state['page'] == 'login':
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("🔐 تسجيل الدخول")
        with st.form("login_form"):
            email = st.text_input("البريد الإلكتروني", placeholder="admin@example.com")
            password = st.text_input("كلمة المرور", type="password")
            submitted = st.form_submit_button("دخول", use_container_width=True)

        if submitted:
            user = login(email.strip(), password)
            if user:
                st.session_state['user_id'] = user.id
                st.session_state['user_name'] = user.name
                st.session_state['user_role'] = user.role
                st.session_state['page'] = 'dashboard'
                # ✅ إصلاح: st.rerun() بدلاً من st.experimental_rerun() المحذوفة
                st.rerun()
            else:
                st.error("❌ بيانات غير صحيحة")

# ===================== الصفحات المحمية =====================
if 'user_id' in st.session_state and st.session_state.get('page') != 'login':
    user = get_user(st.session_state['user_id'])

    # حالة استثنائية: المستخدم غير موجود في قاعدة البيانات
    if not user:
        st.error("خطأ: المستخدم غير موجود. يرجى تسجيل الدخول مجدداً.")
        st.session_state.clear()
        st.rerun()

    # --- الشريط الجانبي ---
    with st.sidebar:
        st.markdown(f"### 👤 {user.name}")
        st.caption(f"الدور: {'مدير' if user.role == 'admin' else 'مستخدم'}")
        st.divider()

        # ✅ إصلاح: بناء قائمة التنقل بدون None
        menu_options = ["📊 Dashboard", "✅ مهام اليوم", "📋 المهام"]
        if user.role == 'admin':
            menu_options.append("👥 المستخدمون")

        menu = st.radio("القائمة", menu_options)
        st.divider()

        if st.button("🚪 تسجيل خروج", use_container_width=True):
            st.session_state.clear()
            st.rerun()

    # ===================== Dashboard =====================
    if menu == "📊 Dashboard":
        st.header("📊 لوحة التقدم")
        today = date.today()
        st.caption(f"اليوم: {today.strftime('%Y-%m-%d')}")

        instances = session.query(TaskInstance).filter_by(date=today).all()
        rows = []
        for inst in instances:
            u = get_user(inst.completed_by) if inst.completed_by else None
            task = get_task(inst.task_id)
            rows.append({
                "المستخدم": u.name if u else "غير مكتمل",
                "المهمة": task.title if task else f"#{inst.task_id}",
                "النقاط": inst.points_awarded or 0,
                "الحالة": "✅ مكتملة" if inst.status == 'done' else "⏳ معلقة"
            })

        if not rows:
            st.info("لا توجد بيانات لليوم")
        else:
            df = pd.DataFrame(rows)
            agg = df.groupby('المستخدم', as_index=False)['النقاط'].sum()
            fig = px.bar(
                agg, x='المستخدم', y='النقاط',
                title='نقاط كل مستخدم اليوم',
                color='النقاط', color_continuous_scale='Blues'
            )
            st.plotly_chart(fig, use_container_width=True)

            st.subheader("تفاصيل المهام")
            st.dataframe(df, use_container_width=True)

            total = df['النقاط'].sum()
            st.metric("إجمالي النقاط اليوم", f"{total:.1f}")

    # ===================== مهام اليوم =====================
    elif menu == "✅ مهام اليوم":
        st.header("✅ مهام اليوم")
        today = date.today()
        st.caption(f"اليوم: {today.strftime('%Y-%m-%d')}")

        # فلترة المهام حسب صلاحية المستخدم
        if user.role == 'admin':
            instances = session.query(TaskInstance).filter_by(date=today).all()
        else:
            # عرض المهام الخاصة بالمستخدم أو مجموعته أو العامة
            all_instances = session.query(TaskInstance).filter_by(date=today).all()
            instances = []
            for inst in all_instances:
                task = get_task(inst.task_id)
                if task and (
                    task.is_global or
                    task.assigned_to == user.id or
                    (task.assigned_group_id and task.assigned_group_id == user.group_id)
                ):
                    instances.append(inst)

        if not instances:
            st.info("لا توجد مهام لليوم. يمكن إنشاؤها من صفحة المهام.")
        else:
            for inst in instances:
                task = get_task(inst.task_id)
                task_title = task.title if task else f"مهمة #{inst.task_id}"

                with st.expander(f"{'✅' if inst.status == 'done' else '⏳'} {task_title}", expanded=(inst.status != 'done')):
                    if task and task.description:
                        st.write(task.description)

                    col1, col2, col3 = st.columns([2, 2, 1])
                    with col1:
                        st.write(f"**الهدف:** {inst.target_value} {task.unit_name if task else ''}")
                        if inst.completed_by:
                            completer = get_user(inst.completed_by)
                            st.write(f"**أُنجز بواسطة:** {completer.name if completer else 'غير معروف'}")
                    with col2:
                        val = st.number_input(
                            "قيمة الإنجاز",
                            value=float(inst.completed_value or 0.0),
                            min_value=0.0,
                            key=f"val_{inst.id}",
                            disabled=(inst.status == 'done' and user.role != 'admin')
                        )
                    with col3:
                        st.write("")  # مسافة للمحاذاة
                        if st.button("💾 تسجيل", key=f"btn_{inst.id}", use_container_width=True):
                            points = compute_points(val, task.points_per_unit if task else 1.0)
                            inst.completed_value = val
                            inst.completed_by = user.id
                            inst.status = 'done'
                            inst.points_awarded = points
                            session.commit()
                            st.success(f"✅ تم تسجيل {points:.1f} نقطة")
                            st.rerun()

    # ===================== المهام =====================
    elif menu == "📋 المهام":
        st.header("📋 إدارة المهام")

        # ✅ التحقق من الصلاحية
        if user.role != 'admin':
            st.warning("⚠️ يمكن للمديرين فقط إنشاء المهام. يمكنك مشاهدة القائمة أدناه.")
        else:
            st.subheader("إنشاء مهمة جديدة")
            with st.form("create_task"):
                title = st.text_input("عنوان المهمة")
                desc = st.text_area("وصف")
                col1, col2 = st.columns(2)
                with col1:
                    is_global = st.checkbox("مهمة للجميع")
                    points_per_unit = st.number_input("نقاط لكل وحدة", value=1.0, min_value=0.1)
                    unit_name = st.text_input("اسم الوحدة (مثلاً: صفحة)")
                with col2:
                    users_list = session.query(User).all()
                    groups_list = session.query(Group).all()
                    assigned_to = st.selectbox(
                        "تعيين لمستخدم (اختياري)",
                        options=[None] + [u.id for u in users_list],
                        format_func=lambda x: "—" if x is None else get_user(x).name
                    )
                    assigned_group = st.selectbox(
                        "تعيين لمجموعة (اختياري)",
                        options=[None] + [g.id for g in groups_list],
                        format_func=lambda x: "—" if x is None else get_group(x).name
                    )
                submitted = st.form_submit_button("✅ إنشاء المهمة", use_container_width=True)

            if submitted:
                if not title.strip():
                    st.error("يرجى إدخال عنوان المهمة")
                else:
                    t = Task(
                        title=title.strip(), description=desc,
                        is_global=is_global, assigned_to=assigned_to,
                        assigned_group_id=assigned_group,
                        points_per_unit=points_per_unit,
                        unit_name=unit_name, created_by=user.id
                    )
                    session.add(t)
                    session.commit()
                    st.success("✅ تم إنشاء المهمة")
                    st.rerun()

            st.divider()
            st.subheader("إنشاء نسخة يومية (TaskInstance)")
            task_options = session.query(Task).all()
            if task_options:
                sel = st.selectbox(
                    "اختر مهمة",
                    options=[None] + [t.id for t in task_options],
                    format_func=lambda x: "—" if x is None else get_task(x).title
                )
                target = st.number_input("القيمة المستهدفة", value=0.0, min_value=0.0)
                if sel and st.button("➕ إنشاء نسخة لليوم"):
                    today = date.today()
                    exists = session.query(TaskInstance).filter_by(task_id=sel, date=today).first()
                    if exists:
                        st.warning("⚠️ موجود بالفعل لليوم")
                    else:
                        ti = TaskInstance(task_id=sel, date=today, target_value=target)
                        session.add(ti)
                        session.commit()
                        st.success("✅ تم الإنشاء")
                        st.rerun()

        st.subheader("قائمة المهام")
        tasks = session.query(Task).all()
        if not tasks:
            st.info("لا توجد مهام بعد")
        else:
            for t in tasks:
                assigned_name = get_user(t.assigned_to).name if t.assigned_to else "—"
                group_name = get_group(t.assigned_group_id).name if t.assigned_group_id else "—"
                st.write(
                    f"- **{t.title}** | الوحدة: `{t.unit_name or '—'}` "
                    f"| نقاط/وحدة: `{t.points_per_unit}` "
                    f"| للجميع: `{'✅' if t.is_global else '❌'}` "
                    f"| مستخدم: `{assigned_name}` | مجموعة: `{group_name}`"
                )

    # ===================== المستخدمون (مدير فقط) =====================
    elif menu == "👥 المستخدمون" and user.role == 'admin':
        st.header("👥 إدارة المستخدمين والمجموعات")

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("إنشاء مجموعة")
            with st.form("create_group"):
                gname = st.text_input("اسم المجموعة")
                if st.form_submit_button("✅ إنشاء مجموعة", use_container_width=True):
                    if not gname.strip():
                        st.error("يرجى إدخال اسم المجموعة")
                    else:
                        grp = Group(name=gname.strip())
                        session.add(grp)
                        session.commit()
                        st.success("✅ تم إنشاء المجموعة")
                        st.rerun()

        with col2:
            st.subheader("إنشاء مستخدم")
            with st.form("create_user"):
                uname = st.text_input("الاسم")
                uemail = st.text_input("البريد")
                upass = st.text_input("كلمة المرور", type="password")
                urole = st.selectbox("الدور", options=["user", "admin"], format_func=lambda x: "مدير" if x == "admin" else "مستخدم")
                groups_list = session.query(Group).all()
                gid = st.selectbox(
                    "اختر مجموعة (اختياري)",
                    options=[None] + [g.id for g in groups_list],
                    format_func=lambda x: "—" if x is None else get_group(x).name
                )
                if st.form_submit_button("✅ إنشاء مستخدم", use_container_width=True):
                    if not uname.strip() or not uemail.strip() or not upass:
                        st.error("يرجى ملء جميع الحقول المطلوبة")
                    elif get_user_by_email(uemail.strip()):
                        st.error("❌ البريد موجود مسبقاً")
                    else:
                        new_user = User(
                            name=uname.strip(),
                            email=uemail.strip(),
                            password_hash=generate_password_hash(upass),
                            role=urole,
                            group_id=gid
                        )
                        session.add(new_user)
                        session.commit()
                        st.success("✅ تم إنشاء المستخدم")
                        st.rerun()

        st.divider()
        st.subheader("قائمة المستخدمين")
        users_list = session.query(User).all()
        users_data = [{
            "الاسم": u.name,
            "البريد": u.email,
            "الدور": "مدير" if u.role == "admin" else "مستخدم",
            "المجموعة": u.group.name if u.group else "—"
        } for u in users_list]
        st.dataframe(pd.DataFrame(users_data), use_container_width=True)

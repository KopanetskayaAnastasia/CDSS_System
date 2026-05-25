#python
"""
Streamlit UI для СППВР
"""

import streamlit as st
import requests
import json
from datetime import datetime, timedelta
import os

st.set_page_config(page_title="СППВР - Система поддержки принятия врачебных решений", page_icon="🏥", layout="wide")

# === CSS (оставлен как в оригинале) ===
st.markdown("""
<style>
    .stApp { background: linear-gradient(135deg, #0e1117 0%, #1a1f2e 100%); }
    .main-header { background: linear-gradient(90deg, #1f6eeb 0%, #0e4bc0 100%); padding: 1rem; border-radius: 15px; margin-bottom: 1rem; }
    .main-header h1 { color: white; margin: 0; font-size: 1.5rem; }
    .main-header p { color: rgba(255,255,255,0.85); margin: 0.2rem 0 0 0; }
    [data-testid="stSidebar"] { background: linear-gradient(180deg, #161b22 0%, #0d1117 100%); }
    .stButton > button { background: linear-gradient(90deg, #1f6eeb 0%, #1557c4 100%); color: white; border: none; border-radius: 8px; }
    .stButton > button:hover { transform: translateY(-2px); }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; background: #1e1e2a; border-radius: 12px; padding: 5px; }
    .stTabs [data-baseweb="tab"] { border-radius: 8px; padding: 8px 16px; color: #a0a0c0; }
    .stTabs [aria-selected="true"] { background: #1f6eeb; color: white; }
    ::-webkit-scrollbar { width: 8px; }
    ::-webkit-scrollbar-track { background: #1a1f2e; }
    ::-webkit-scrollbar-thumb { background: #1f6eeb; border-radius: 10px; }
</style>
""", unsafe_allow_html=True)

# === ЗАГОЛОВОК ===
st.markdown("""
<div class="main-header">
    <h1>🏥 Система поддержки принятия врачебных решений</h1>
    <p>Семантический поиск в клинических рекомендациях на основе RAG-архитектуры</p>
</div>
""", unsafe_allow_html=True)

# === ИНИЦИАЛИЗАЦИЯ ===
if "messages" not in st.session_state:
    st.session_state.messages = []
if "session_id" not in st.session_state:
    st.session_state.session_id = None
if "token" not in st.session_state:
    st.session_state.token = None
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_role" not in st.session_state:
    st.session_state.user_role = None
if "user_name" not in st.session_state:
    st.session_state.user_name = None
if "selected_patient_id" not in st.session_state:
    st.session_state.selected_patient_id = None
if "conversation_history" not in st.session_state:
    st.session_state.conversation_history = {}

API_URL = os.getenv("API_URL", "http://localhost:8000")  # ← ИСПРАВЛЕНО

def get_user_info(token: str) -> dict:
    try:
        import base64
        import json
        
        # Разделяем JWT токен
        parts = token.split('.')
        if len(parts) < 2:
            return {"role": "Doctor", "login": "unknown"}
        
        # Декодируем payload (вторая часть)
        payload_base64 = parts[1]
        # Добавляем padding если нужно
        padding = 4 - len(payload_base64) % 4
        if padding != 4:
            payload_base64 += '=' * padding
        
        payload_json = base64.b64decode(payload_base64).decode('utf-8')
        payload = json.loads(payload_json)
        
        role_id = payload.get("role_id", 1)
        login = payload.get("login", "unknown")
        
        print(f"DEBUG: role_id={role_id}, login={login}")  # Для отладки в логах
        
        return {"role": "Admin" if role_id == 2 else "Doctor", "login": login}
    except Exception as e:
        print(f"Error decoding token: {e}")
        return {"role": "Doctor", "login": "unknown"}

def login():
    st.sidebar.markdown("## 🔐 Авторизация")
    with st.sidebar.form("login_form"):
        login = st.text_input("Логин")
        password = st.text_input("Пароль", type="password")
        submitted = st.form_submit_button("🔓 Войти", use_container_width=True)
        if submitted:
            try:
                response = requests.post(f"{API_URL}/auth/login", json={"login": login, "password": password}, timeout=6000)
                if response.status_code == 200:
                    data = response.json()
                    st.session_state.token = data["access_token"]
                    user_info = get_user_info(data["access_token"])
                    st.session_state.logged_in = True
                    st.session_state.user_role = user_info["role"]
                    st.session_state.user_name = login
                    st.rerun()
                else:
                    st.error("❌ Неверный логин или пароль")
            except Exception as e:
                st.error(f"❌ Ошибка: {e}")
    st.sidebar.markdown("---")
    st.sidebar.info("**Демо:**\n👨‍⚕️ doctor / doctor123\n👨‍💼 admin / admin123")


def logout():
    for key in ["token", "logged_in", "user_role", "user_name", "messages", "session_id", "selected_patient_id", "selected_patient_name"]:
        st.session_state[key] = None if key not in ["messages"] else []
    st.session_state.logged_in = False
    st.rerun()


def send_message(query: str):
    if not query.strip():
        return

    st.session_state.messages.append({"role": "user", "content": query})

    try:
        headers = {"Authorization": f"Bearer {st.session_state.token}"}
        payload = {"query": query, "session_id": st.session_state.session_id,
                   "patient_id": st.session_state.selected_patient_id}

        with st.spinner("🔍 Анализирую клинические рекомендации..."):
            response = requests.post(f"{API_URL}/chat", json=payload, headers=headers, timeout=60)

        if response.status_code == 200:
            data = response.json()
            st.session_state.session_id = data["session_id"]
            answer = data["answer"]
            citations = data.get("citations", [])
            confidence = data.get("confidence", 0.0)

            st.session_state.messages.append({"role": "assistant", "content": answer, "citations": citations})

            with st.chat_message("assistant"):
                st.markdown(answer)

                # ОТОБРАЖЕНИЕ CONFIDENCE
                if confidence >= 0.7:
                    st.success(f"🎯 Уровень доверенности: {confidence * 100:.1f}%")
                elif confidence >= 0.4:
                    st.warning(f"⚠️ Уровень доверенности: {confidence * 100:.1f}%")
                else:
                    st.error(f"❓ Уровень доверенности: {confidence * 100:.1f}% (низкий, проверьте источники)")

                if citations:
                    with st.expander("📚 Источники (нажмите на ссылку, чтобы открыть PDF)"):
                        for c in citations:
                            guideline_id = c.get('guideline_id')
                            source_title = c.get('source_title', 'Неизвестный источник')
                            page_number = c.get('page_number', 0)

                            st.markdown(f"**[{c.get('citation_order', '?')}]** {source_title}")
                            if page_number:
                                st.caption(f"📄 Страница: {page_number}")

                            if guideline_id:
                                pdf_url = f"http://localhost:8000/guidelines/{guideline_id}/pdf"
                                st.markdown(f"🔗 [Открыть PDF]({pdf_url})")
                            st.divider()

            # Сохранение в историю
            session_key = st.session_state.session_id
            if session_key not in st.session_state.conversation_history:
                st.session_state.conversation_history[session_key] = []
            st.session_state.conversation_history[session_key].append({
                "role": "assistant",
                "content": answer,
                "citations": citations,
                "confidence": confidence,
                "timestamp": datetime.now().isoformat()
            })
        else:
            st.error(f"❌ Ошибка API: {response.status_code}")
    except Exception as e:
        st.error(f"❌ {e}")

def load_history_session(session_id: str):
    if session_id in st.session_state.conversation_history:
        st.session_state.messages = st.session_state.conversation_history[session_id]
        st.session_state.session_id = session_id
        st.rerun()


def delete_history_session(session_id: str):
    if session_id in st.session_state.conversation_history:
        del st.session_state.conversation_history[session_id]
    if st.session_state.session_id == session_id:
        st.session_state.messages = []
        st.session_state.session_id = None
    st.rerun()


def export_history():
    if st.session_state.conversation_history:
        data = {
            "export_date": datetime.now().isoformat(),
            "user": st.session_state.user_name,
            "sessions": st.session_state.conversation_history
        }
        return json.dumps(data, ensure_ascii=False, indent=2)
    return None


def history_panel():
    st.sidebar.markdown("---")
    st.sidebar.markdown("## 📜 История диалогов")

    if not st.session_state.conversation_history:
        st.sidebar.info("Нет сохранённых диалогов")
        return

    sessions = []
    for sid, msgs in st.session_state.conversation_history.items():
        if msgs:
            last_time = msgs[-1].get("timestamp", "1970-01-01T00:00:00")
            first_msg = msgs[0].get("content", "Новый диалог")[:40]
            sessions.append({"id": sid, "last_time": last_time, "preview": first_msg})

    sessions.sort(key=lambda x: x["last_time"], reverse=True)

    for s in sessions:
        col1, col2 = st.sidebar.columns([4, 1])
        with col1:
            if st.button(f"💬 {s['preview']}...", key=f"load_{s['id']}", use_container_width=True):
                load_history_session(s["id"])
        with col2:
            if st.button("🗑️", key=f"del_{s['id']}"):
                delete_history_session(s["id"])

    st.sidebar.markdown("---")
    export_data = export_history()
    if export_data:
        st.sidebar.download_button(
            label="📎 Экспорт всей истории",
            data=export_data,
            file_name=f"cdss_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json",
            use_container_width=True
        )

    if st.sidebar.button("🗑️ Очистить всю историю", use_container_width=True):
        st.session_state.conversation_history = {}
        st.session_state.messages = []
        st.session_state.session_id = None
        st.rerun()


# ========== АДМИН-СТРАНИЦЫ ==========
def guidelines_page():
    st.markdown("## 📚 Клинические рекомендации")
    headers = {"Authorization": f"Bearer {st.session_state.token}"}

    if st.button("🔄 Обновить список", use_container_width=True):
        st.rerun()

    response = requests.get(f"{API_URL}/admin/guidelines", headers=headers)
    if response.status_code != 200:
        st.error("Не удалось загрузить список КР")
        return

    guidelines = response.json()
    if not guidelines:
        st.info("📭 Нет загруженных клинических рекомендаций.")
        return

    st.markdown(f"**Всего КР: {len(guidelines)}**")
    st.markdown("---")

    for g in guidelines:
        col1, col2, col3, col4, col5, col6 = st.columns([3, 1, 1, 1, 1, 1])
        with col1:
            st.markdown(f"**{g['title']}**")
            st.caption(f"Версия: {g['version']} ({g['year']}) | ID: {g['id']}")
        with col2:
            st.write(f"📄 {g['total_chunks']} чанков")
        with col3:
            st.markdown("🟢 Активна" if g['is_active'] else "🔴 Неактивна")
        with col4:
            if st.button("🔄 Акт/деакт", key=f"toggle_cr_{g['id']}"):
                requests.put(f"{API_URL}/admin/guidelines/{g['id']}/toggle", headers=headers)
                st.rerun()
        with col5:
            if st.button("🔄 Переинд", key=f"reindex_{g['id']}"):
                headers = {"Authorization": f"Bearer {st.session_state.token}"}
                response = requests.post(
                    f"{API_URL}/admin/reindex/{g['id']}",
                    headers=headers,
                    timeout=300
                )
                if response.status_code == 200:
                    st.success(f"✅ {g['title']} переиндексирована")
                    st.rerun()
                else:
                    st.error(f"❌ Ошибка")
        with col6:
            if st.button("🗑️ Удалить", key=f"del_cr_{g['id']}"):
                if st.checkbox(f"Подтвердить удаление {g['title']}", key=f"confirm_{g['id']}"):
                    requests.delete(f"{API_URL}/admin/guidelines/{g['id']}", headers=headers)
                    st.rerun()
        st.divider()


def patients_page():
    st.markdown("## 👥 Управление пациентами")
    with st.expander("➕ Добавить пациента", expanded=False):
        with st.form("add_patient_form"):
            full_name = st.text_input("ФИО")
            col1, col2 = st.columns(2)
            with col1:
                snils = st.text_input("СНИЛС")
                date_of_birth = st.date_input("Дата рождения", value=None)
            with col2:
                policy_number = st.text_input("Номер полиса")
            submitted = st.form_submit_button("Добавить")
            if submitted and full_name:
                headers = {"Authorization": f"Bearer {st.session_state.token}"}
                requests.post(f"{API_URL}/patients", json={"full_name": full_name, "snils": snils, "policy_number": policy_number, "date_of_birth": date_of_birth.isoformat() if date_of_birth else None}, headers=headers)
                st.rerun()

    st.markdown("### 📋 Список пациентов")
    headers = {"Authorization": f"Bearer {st.session_state.token}"}
    response = requests.get(f"{API_URL}/patients", headers=headers)
    if response.status_code == 200:
        patients = response.json()
        for p in patients:
            col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
            with col1:
                st.write(f"**{p['full_name']}**")
                st.caption(f"ID: {p['id']}")
            with col2:
                st.write(p.get('snils', '—'))
            with col3:
                st.write(p.get('policy_number', '—'))
            with col4:
                if st.button("🗑️", key=f"del_p_{p['id']}"):
                    if st.session_state.user_role == "Admin":
                        requests.delete(f"{API_URL}/patients/{p['id']}", headers=headers)
                        st.rerun()
            st.divider()


def doctors_page():
    st.markdown("## 👨‍⚕️ Управление врачами")
    if st.session_state.user_role != "Admin":
        st.warning("Доступно только администратору")
        return

    with st.expander("➕ Добавить врача", expanded=False):
        with st.form("add_doctor_form"):
            col1, col2 = st.columns(2)
            with col1:
                login = st.text_input("Логин")
                full_name = st.text_input("ФИО")
            with col2:
                password = st.text_input("Пароль", type="password")
                specialty = st.text_input("Специальность")
            submitted = st.form_submit_button("Добавить")
            if submitted and login and password and full_name:
                headers = {"Authorization": f"Bearer {st.session_state.token}"}
                requests.post(f"{API_URL}/admin/doctors", json={"login": login, "password": password, "full_name": full_name, "specialty": specialty}, headers=headers)
                st.rerun()

    st.markdown("### 📋 Список врачей")
    headers = {"Authorization": f"Bearer {st.session_state.token}"}
    response = requests.get(f"{API_URL}/admin/doctors", headers=headers)
    if response.status_code == 200:
        doctors = response.json()
        for d in doctors:
            col1, col2, col3, col4, col5 = st.columns([2, 3, 2, 1, 1])
            with col1:
                st.write(f"**{d['login']}**")
                st.caption(f"ID: {d['id']}")
            with col2:
                st.write(d['full_name'])
            with col3:
                st.write(d.get('specialty', '—'))
            with col4:
                st.write("✅ Активен" if d['is_active'] else "❌ Деактивирован")
            with col5:
                if st.button("🔄", key=f"toggle_{d['id']}"):
                    requests.put(f"{API_URL}/admin/doctors/{d['id']}/toggle", headers=headers)
                    st.rerun()
            st.divider()


def upload_kr_page():
    st.markdown("## 📄 Загрузка клинической рекомендации")
    with st.form("upload_form"):
        uploaded_file = st.file_uploader("PDF файл", type=["pdf"])
        col1, col2 = st.columns(2)
        with col1:
            title = st.text_input("Название")
            version = st.text_input("Версия")
        with col2:
            year = st.number_input("Год", min_value=2000, max_value=2030, value=2024)
        submitted = st.form_submit_button("📤 Загрузить")
        if submitted and uploaded_file and title and version:
            files = {"file": (uploaded_file.name, uploaded_file.getvalue(), "application/pdf")}
            data = {"title": title, "version": version, "year": year}
            headers = {"Authorization": f"Bearer {st.session_state.token}"}
            with st.spinner("Обработка PDF и индексация..."):
                response = requests.post(f"{API_URL}/admin/upload", files=files, data=data, headers=headers, timeout=600)
            if response.status_code == 200:
                st.success("✅ КР успешно загружена!")
                st.rerun()
            else:
                st.error(f"❌ {response.json().get('detail', 'Ошибка')}")


def status_page():
    st.markdown("## 📊 Статус базы знаний")
    headers = {"Authorization": f"Bearer {st.session_state.token}"}
    response = requests.get(f"{API_URL}/admin/status", headers=headers)
    if response.status_code == 200:
        status = response.json()
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("📚 Активных КР", status.get("active_guidelines", 0))
        with col2:
            st.metric("📄 Всего КР", status.get("total_guidelines", 0))
        with col3:
            st.metric("📄 Всего фрагментов", status.get("total_chunks", 0))
        with col4:
            st.metric("💾 ChromaDB чанков", status.get("chroma_chunk_count", 0))
    else:
        st.error("Не удалось получить статус")


def select_patient_sidebar():
    st.sidebar.markdown("---")
    st.sidebar.markdown("## 🩺 Пациент")
    headers = {"Authorization": f"Bearer {st.session_state.token}"}
    response = requests.get(f"{API_URL}/patients", headers=headers)
    patients = [{"id": None, "full_name": "🚫 Без пациента"}]
    if response.status_code == 200:
        patients.extend(response.json())
    selected_name = st.sidebar.selectbox("Выберите пациента", options=[p["full_name"] for p in patients], index=0)
    for p in patients:
        if p["full_name"] == selected_name:
            st.session_state.selected_patient_id = p["id"]
            st.session_state.selected_patient_name = None if p["id"] is None else selected_name
            break
    if st.session_state.selected_patient_id:
        st.sidebar.success(f"👤 {selected_name}")


def chat_interface():
    """Отображение чата и поля ввода (вынесено за пределы tabs)"""
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg["role"] == "assistant" and msg.get("citations"):
                with st.expander("📚 Показать источники"):
                    for c in msg["citations"]:
                        st.markdown(f"**[{c.get('citation_order', '?')}]** {c.get('source_title', 'Unknown')}")
                        if c.get('section'): st.markdown(f"📖 Раздел: {c.get('section')}")
                        if c.get('page_number'): st.markdown(f"📄 Страница: {c.get('page_number')}")
                        st.markdown("---")

    if prompt := st.chat_input("💬 Введите ваш клинический вопрос..."):
        send_message(prompt)


# ========== НОВЫЕ АДМИН-СТРАНИЦЫ ==========

def upload_multiple_kr_page():
    """Страница пакетной загрузки КР"""
    st.markdown("## 📦 Пакетная загрузка клинических рекомендаций")
    st.markdown("Загрузите несколько PDF-файлов одновременно")

    uploaded_files = st.file_uploader(
        "Выберите PDF файлы (можно несколько)",
        type=["pdf"],
        accept_multiple_files=True
    )

    if st.button("📤 Загрузить все файлы", use_container_width=True):
        if uploaded_files:
            headers = {"Authorization": f"Bearer {st.session_state.token}"}

            for file in uploaded_files:
                files = {"files": (file.name, file.getvalue(), "application/pdf")}

                with st.spinner(f"Загрузка {file.name}..."):
                    response = requests.post(
                        f"{API_URL}/admin/upload-multiple",
                        files=files,
                        headers=headers,
                        timeout=300
                    )

                if response.status_code == 200:
                    st.success(f"✅ {file.name} загружен")
                else:
                    st.error(f"❌ {file.name}: {response.json().get('detail', 'Ошибка')}")

            st.rerun()
        else:
            st.warning("Выберите файлы")


def reindex_all_page():
    """Страница переиндексации всех КР"""
    st.markdown("## 🔄 Переиндексация базы знаний")
    st.markdown("Это может занять несколько минут в зависимости от количества КР")

    if st.button("🔄 Переиндексировать все КР", use_container_width=True):
        headers = {"Authorization": f"Bearer {st.session_state.token}"}

        with st.spinner("Переиндексация запущена. Это может занять несколько минут..."):
            response = requests.post(
                f"{API_URL}/admin/reindex-all",
                headers=headers,
                timeout=600  # ← ИЗМЕНИТЬ с 10 на 600
            )

        if response.status_code == 200:
            st.success("✅ Переиндексация запущена в фоновом режиме")
            st.info("Статус можно проверить через 5-10 минут в разделе 'Статус базы знаний'")
        else:
            st.error(f"❌ Ошибка: {response.json().get('detail', 'Неизвестная ошибка')}")


def admin_panel():
    admin_tabs = st.tabs([
        "📄 Загрузить КР",
        "📦 Пакетная загрузка",   # НОВАЯ
        "🔄 Переиндексация",       # НОВАЯ
        "📚 Управление КР",
        "👥 Пациенты",
        "👨‍⚕️ Врачи",
        "📊 Статус",
        "📋 Журнал аудита",
        "📈 Статистика",
        "🔧 Роли",
        "📜 Диалоги"
    ])

    with admin_tabs[0]:
        upload_kr_page()
    with admin_tabs[1]:
        upload_multiple_kr_page()
    with admin_tabs[2]:
        reindex_all_page()
    with admin_tabs[3]:
        guidelines_page()
    with admin_tabs[4]:
        patients_page()
    with admin_tabs[5]:
        doctors_page()
    with admin_tabs[6]:
        status_page()
    with admin_tabs[7]:
        audit_logs_page()
    with admin_tabs[8]:
        stats_page()
    with admin_tabs[9]:
        roles_page()
    with admin_tabs[10]:
        admin_dialogues_page()

# ========== НОВЫЕ АДМИН-СТРАНИЦЫ ==========

def audit_logs_page():
    """Страница журнала аудита"""
    st.markdown("## 📋 Журнал аудита")
    st.markdown("Все действия пользователей в системе")

    headers = {"Authorization": f"Bearer {st.session_state.token}"}

    # Фильтры
    col1, col2, col3 = st.columns(3)
    with col1:
        action_filter = st.selectbox(
            "Тип действия",
            ["Все", "login", "logout", "query", "upload_kr", "delete_guideline",
             "add_doctor", "delete_doctor", "toggle_doctor", "add_patient", "delete_patient"],
            index=0
        )
    with col2:
        days_back = st.selectbox("Период", ["Все", "1 день", "7 дней", "30 дней"], index=0)
    with col3:
        limit = st.selectbox("Записей на страницу", [50, 100, 200], index=0)

    # Параметры запроса
    params = {"limit": limit, "offset": 0}
    if action_filter != "Все":
        params["action_type"] = action_filter
    if days_back != "Все":
        days = int(days_back.split()[0])
        from_date = (datetime.now() - timedelta(days=days)).isoformat()
        params["from_date"] = from_date

    response = requests.get(f"{API_URL}/admin/audit-logs", headers=headers, params=params)

    if response.status_code == 200:
        data = response.json()
        logs = data.get("logs", [])

        if not logs:
            st.info("Нет записей в журнале аудита")
            return

        st.caption(f"Всего записей: {data.get('total', 0)}")

        # Таблица с логами
        for log in logs:
            with st.container():
                col1, col2, col3, col4 = st.columns([2, 2, 2, 3])
                with col1:
                    st.markdown(f"**{log.get('action_type', '?')}**")
                    st.caption(log.get('timestamp', '')[:19] if log.get('timestamp') else '')
                with col2:
                    st.write(f"👨‍⚕️ {log.get('doctor_login', 'Unknown')}")
                with col3:
                    if log.get('patient_id'):
                        st.write(f"🩺 Пациент ID: {log.get('patient_id')}")
                    else:
                        st.write("—")
                with col4:
                    details = log.get('action_details', {})
                    if isinstance(details, str):
                        try:
                            details = json.loads(details)
                        except:
                            pass
                    st.caption(str(details)[:100] + "..." if len(str(details)) > 100 else str(details))
                if log.get('is_abnormal'):
                    st.error(f"⚠️ Нештатная ситуация: {log.get('abnormal_reason', 'Неизвестно')}")
                st.divider()
    else:
        st.error("Не удалось загрузить журнал аудита")


def stats_page():
    """Страница расширенной статистики"""
    st.markdown("## 📈 Статистика использования")

    headers = {"Authorization": f"Bearer {st.session_state.token}"}
    response = requests.get(f"{API_URL}/admin/stats", headers=headers)

    if response.status_code == 200:
        stats = response.json()

        # Основные метрики
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("👨‍⚕️ Врачи", stats.get("doctors", {}).get("total", 0))
            st.caption(f"Активных: {stats.get('doctors', {}).get('active', 0)}")
        with col2:
            st.metric("🩺 Пациенты", stats.get("patients", 0))
        with col3:
            st.metric("💬 Диалоги", stats.get("dialogues", 0))
        with col4:
            st.metric("🎯 Средняя уверенность", f"{stats.get('avg_confidence', 0) * 100:.1f}%")

        st.markdown("---")

        # Статистика по КР
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("📚 Клинические рекомендации")
            guidelines = stats.get("guidelines", {})
            st.metric("Всего КР", guidelines.get("total", 0))
            st.metric("Активных КР", guidelines.get("active", 0))
            st.metric("Всего чанков", stats.get("chunks", 0))

        with col2:
            st.subheader("💬 Сообщения")
            messages = stats.get("messages", {})
            st.metric("Всего сообщений", messages.get("total", 0))
            st.metric("Запросов врачей", messages.get("queries", 0))
            st.metric("Ответов системы", messages.get("assistant_responses", 0))

        st.markdown("---")

        # Популярные действия
        st.subheader("📊 Популярные действия")
        popular = stats.get("popular_actions", [])
        if popular:
            for action in popular:
                st.write(f"- {action.get('action', '?')}: {action.get('count', 0)} раз")

        # Дневная активность
        st.subheader("📅 Активность по дням")
        daily = stats.get("daily_activity", [])
        if daily:
            chart_data = {d.get("date", ""): d.get("count", 0) for d in daily}
            st.json(chart_data)
    else:
        st.error("Не удалось загрузить статистику")


def roles_page():
    """Страница управления ролями (просмотр)"""
    st.markdown("## 🔧 Роли пользователей")

    headers = {"Authorization": f"Bearer {st.session_state.token}"}
    response = requests.get(f"{API_URL}/admin/roles", headers=headers)

    if response.status_code == 200:
        roles = response.json()

        if not roles:
            st.info("Нет загруженных ролей")
            return

        for role in roles:
            with st.container():
                col1, col2 = st.columns([1, 3])
                with col1:
                    if role.get("role_name") == "Admin":
                        st.markdown("👨‍💼 **Admin**")
                    else:
                        st.markdown("👨‍⚕️ **Doctor**")
                with col2:
                    st.write(role.get("description", ""))
                    st.caption(f"ID: {role.get('id')} | Врачей с этой ролью: {role.get('doctors_count', 0)}")
                st.divider()
    else:
        st.error("Не удалось загрузить роли")


def admin_dialogues_page():
    """Страница просмотра всех диалогов (для админа)"""
    st.markdown("## 📜 История всех диалогов")

    headers = {"Authorization": f"Bearer {st.session_state.token}"}

    # Фильтры
    col1, col2 = st.columns(2)
    with col1:
        doctor_filter = st.text_input("ID врача (опционально)", placeholder="Введите ID врача")
    with col2:
        patient_filter = st.text_input("ID пациента (опционально)", placeholder="Введите ID пациента")

    params = {"limit": 50, "offset": 0}
    if doctor_filter and doctor_filter.isdigit():
        params["doctor_id"] = int(doctor_filter)
    if patient_filter and patient_filter.isdigit():
        params["patient_id"] = int(patient_filter)

    response = requests.get(f"{API_URL}/admin/dialogues", headers=headers, params=params)

    if response.status_code == 200:
        data = response.json()
        dialogues = data.get("dialogues", [])

        if not dialogues:
            st.info("Нет диалогов")
            return

        st.caption(f"Всего диалогов: {data.get('total', 0)}")

        for d in dialogues:
            with st.expander(
                    f"💬 Диалог #{d.get('id')} | Врач: {d.get('doctor_name', '?')} | Пациент: {d.get('patient_name', 'Без пациента')} | Сообщений: {d.get('message_count', 0)}"):

                col1, col2 = st.columns(2)

                with col1:
                    st.caption(f"Статус: {d.get('status', 'unknown')}")
                    st.caption(f"Дата: {d.get('started_at', '?')[:19] if d.get('started_at') else '?'}")

                with col2:
                    # КНОПКА ЭКСПОРТА PDF
                    if st.button(f"📎 Экспорт в PDF", key=f"export_{d.get('id')}"):
                        try:
                            headers = {"Authorization": f"Bearer {st.session_state.token}"}
                            export_response = requests.get(
                                f"{API_URL}/dialogues/{d.get('id')}/export",
                                headers=headers,
                                timeout=30
                            )
                            if export_response.status_code == 200:
                                st.download_button(
                                    label="📥 Скачать PDF",
                                    data=export_response.content,
                                    file_name=f"dialogue_{d.get('id')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                                    mime="application/pdf",
                                    key=f"download_{d.get('id')}"
                                )
                            else:
                                st.error(f"Ошибка: {export_response.status_code}")
                        except Exception as e:
                            st.error(f"Ошибка экспорта: {e}")
    else:
        st.error("Не удалось загрузить диалоги")


def home_page():
    st.markdown("""
    <div style="text-align: center; padding: 2rem;">
        <h2>👋 Добро пожаловать в СППВР</h2>
        <p>Система поддержки принятия врачебных решений</p>
        <p style="color: #666;">Авторизуйтесь в боковой панели для начала работы</p>
    </div>
    """, unsafe_allow_html=True)


# === ОСНОВНОЙ КОД ===
with st.sidebar:
    if st.session_state.logged_in:
        st.markdown(f"### {'👨‍💼' if st.session_state.user_role == 'Admin' else '👨‍⚕️'} {st.session_state.user_name}")
        st.markdown(f"*{st.session_state.user_role}*")
        select_patient_sidebar()
        history_panel()
        st.markdown("---")
        if st.button("🚪 Выйти", use_container_width=True):
            logout()
    else:
        login()

if st.session_state.logged_in:
    # Переключение между чатом и админкой (для админа)
    if st.session_state.user_role == "Admin":
        mode = st.radio("", ["💬 Чат", "⚙️ Администрирование"], horizontal=True, label_visibility="collapsed")
        if mode == "💬 Чат":
            chat_interface()
        else:
            admin_panel()
    else:
        chat_interface()
else:
    home_page()
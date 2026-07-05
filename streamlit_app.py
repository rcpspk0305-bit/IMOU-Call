import sys
import os
import pandas as pd
import streamlit as st
import plotly.express as px
from supabase import create_client, Client

# 1. Enforce absolute path resolution instantly
current_dir = os.path.abspath(os.path.dirname(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)
app_dir = os.path.abspath(os.path.join(current_dir, 'app'))
if app_dir not in sys.path:
    sys.path.insert(0, app_dir)

# 2. Pre-cache dependencies on the main thread to block import race conditions
import app.config
import app.supabase_service
import app.imou_poller
import app.telegram_service

def format_to_ist_str(val) -> str:
    if pd.isna(val):
        return "Never"
    try:
        from datetime import datetime, timezone, timedelta
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo("Asia/Kolkata")
        except Exception:
            tz = timezone(timedelta(hours=5, minutes=30))

        if isinstance(val, str):
            val_clean = val.replace("Z", "+00:00")
            dt = datetime.fromisoformat(val_clean)
        else:
            dt = pd.to_datetime(val).to_pydatetime()
            
        dt_ist = dt.astimezone(tz)
        return dt_ist.strftime("%Y-%m-%d %H:%M:%S IST")
    except Exception:
        return str(val)

# Page Configurations
st.set_page_config(
    page_title="Imou-Exotel Security Dashboard",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Explicit Production UUID Matrix
SYSTEM_STATE_UUID = "00000000-0000-0000-0000-000000000001"

def get_config(key: str, default: str = "") -> str:
    val = getattr(app.config.Config, key.upper(), None)
    return str(val) if val is not None else default

@st.cache_resource
def get_supabase_client() -> Client:
    try:
        return app.supabase_service.get_backend_service_client()
    except Exception as e:
        st.warning(f"⚠️ Service role registration failed: {str(e)}")
        st.stop()

try:
    supabase = get_supabase_client()
except Exception as e:
    st.error(f"Supabase context missing: {str(e)}")
    st.stop()

auth_supabase = None
try:
    auth_supabase = app.supabase_service.get_frontend_client()
except Exception as e:
    st.error(f"Auth engine missing: {str(e)}")

if "user" not in st.session_state:
    st.session_state["user"] = None
if "session_token" not in st.session_state:
    st.session_state["session_token"] = None

def handle_logout():
    try:
        auth_supabase.auth.sign_out()
    except Exception:
        pass
    st.session_state["user"] = None
    st.session_state["session_token"] = None
    st.rerun()

# Secure Gatekeeper Login Form
if st.session_state["user"] is None:
    st.markdown("<h1 style='text-align: center; margin-top: 50px;'>🛡️ Imou-Exotel Monitoring Portal</h1>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.write("---")
        with st.form("login_form"):
            st.subheader("Secure Access Sign In")
            email = st.text_input("User Email", placeholder="email@example.com")
            password = st.text_input("Security Password", type="password", placeholder="••••••••")
            submit = st.form_submit_button("Authenticate Access")
            
            if submit:
                if not email or not password:
                    st.error("Credentials missing.")
                else:
                    with st.spinner("Authenticating..."):
                        try:
                            auth_response = auth_supabase.auth.sign_in_with_password({
                                "email": email,
                                "password": password
                            })
                            if auth_response.user and auth_response.session:
                                st.session_state["user"] = auth_response.user
                                st.session_state["session_token"] = auth_response.session.access_token
                                st.rerun()
                            else:
                                st.error("Invalid login parameters.")
                        except Exception as e:
                            st.error(f"Authentication failed: {str(e)}")
    st.stop()

# Post-Authentication Dashboard Layout
st.sidebar.markdown("### 👤 User Information")
st.sidebar.write(f"Logged in as: **{st.session_state['user'].email}**")
st.sidebar.button("🔐 Terminate Session", on_click=handle_logout, use_container_width=True)

st.sidebar.write("---")
st.sidebar.markdown("### ⚙️ System Metadata")
st.sidebar.markdown(f"**Target Device:** `{get_config('IMOU_DEVICE_ID', 'Unconfigured')}`")
st.sidebar.markdown(f"**Poll Interval:** `{get_config('IMOU_POLL_INTERVAL_SECONDS', '600')}s`")

st.title("📊 Security & Notification Monitor Dashboard")
st.write("---")

# Query State using Strict UUID Mapping (Fixes 22P02 Error)
try:
    state_res = supabase.table("system_state").select("is_paused").eq("id", SYSTEM_STATE_UUID).execute()
    db_paused = state_res.data[0]["is_paused"] if state_res.data else False
except Exception as e:
    st.error(f"Error reading status from database: {str(e)}")
    db_paused = False

left_col, right_col = st.columns([1, 2], gap="large")

with left_col:
    st.subheader("🛠️ Control Panel")
    new_paused = st.toggle("⏸️ Pause / Resume All Activities", value=db_paused, key="master_pause_switch")
    
    if new_paused != db_paused:
        with st.spinner("Syncing to database..."):
            try:
                supabase.table("system_state").update({"is_paused": new_paused}).eq("id", SYSTEM_STATE_UUID).execute()
                st.rerun()
            except Exception as e:
                st.error(f"Failed to update database row: {str(e)}")

with right_col:
    st.subheader("📈 System Telemetry Metrics")
    
    # Query using production-ready column name 'triggered_at' (Fixes 42703 Error)
    try:
        logs_query = supabase.table("camera_logs").select("*").order("triggered_at", desc=True).limit(100).execute()
        logs_data = logs_query.data or []
    except Exception as e:
        st.error(f"Error loading logs: {str(e)}")
        logs_data = []

    total_alerts = len(logs_data)
    m_col1, m_col2 = st.columns(2)
    with m_col1:
        st.metric("Monitoring State", "PAUSED" if db_paused else "ACTIVE")
    with m_col2:
        st.metric("Alert Records (Last 100)", total_alerts)

    if logs_data:
        df = pd.DataFrame(logs_data)
        triggered_at_dt = pd.to_datetime(df["triggered_at"])
        if triggered_at_dt.dt.tz is None:
            triggered_at_dt = triggered_at_dt.dt.localize("UTC")
            
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo("Asia/Kolkata")
        except Exception:
            from datetime import timezone, timedelta
            tz = timezone(timedelta(hours=5, minutes=30))
            
        df["triggered_at_ist"] = triggered_at_dt.dt.tz_convert(tz)
        df["date"] = df["triggered_at_ist"].dt.date
        alert_counts = df.groupby("date").size().reset_index(name="Alerts Count")

        fig = px.bar(alert_counts, x="date", y="Alerts Count", template="plotly_dark", color_discrete_sequence=["#EF4444"])
        fig.update_layout(height=260, margin=dict(l=20, r=20, t=40, b=20))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No recorded offline alerts found.")

st.write("---")
st.subheader("📋 Telemetry Logs History")

if logs_data:
    df_logs = pd.DataFrame(logs_data)
    df_logs["Time Stamp"] = df_logs["triggered_at"].apply(format_to_ist_str)
    
    exotel_col = df_logs["exotel_call_triggered"].fillna(False) if "exotel_call_triggered" in df_logs.columns else False
    telegram_col = df_logs["telegram_alert_sent"].fillna(False) if "telegram_alert_sent" in df_logs.columns else False
    df_logs["Exotel/Telegram Dispatched"] = exotel_col | telegram_col
    
    df_logs = df_logs.rename(columns={"device_id": "Device ID", "event_type": "Event Type"})
    st.dataframe(
        df_logs[["Device ID", "Event Type", "Time Stamp", "Exotel/Telegram Dispatched"]],
        column_config={"Time Stamp": st.column_config.TextColumn("Time Stamp"), "Exotel/Telegram Dispatched": st.column_config.CheckboxColumn("Exotel/Telegram Dispatched")},
        use_container_width=True, hide_index=True
    )
else:
    st.info("No logs stored in database.")

# Guarded worker activation at the absolute bottom of execution lifespan
def start_background_workers() -> bool:
    if st.session_state.get('workers_initialized', False):
        return True
    try:
        app.imou_poller.imou_poller.start()
        app.telegram_service.telegram_bot_poller.start()
        st.session_state['workers_initialized'] = True
        return True
    except Exception:
        return False

start_background_workers()
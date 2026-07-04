import sys
import os
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'app')))

import pandas as pd
import streamlit as st
import plotly.express as px
from supabase import create_client, Client
# 1. Page Configuration and Layout
st.set_page_config(
    page_title="Imou-Exotel Security Dashboard",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 2. Design System and CSS overrides for Premium Dark Aesthetics
st.markdown("""
<style>
    /* Metric styling */
    div[data-testid="stMetricValue"] {
        font-size: 2.2rem;
        font-weight: 700;
    }
    div[data-testid="stMetricDelta"] > div {
        font-size: 1rem;
    }
    /* Main Layout Cards styling */
    .dashboard-card {
        border-radius: 12px;
        padding: 24px;
        background-color: #1f2937;
        border: 1px solid #374151;
        margin-bottom: 20px;
    }
    .status-active {
        color: #10B981;
        font-weight: bold;
    }
    .status-paused {
        color: #EF4444;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

from app.config import Config

# Helper function to get config keys from centralized Config (which handles st.secrets / env mapping)
def get_config(key: str, default: str = "") -> str:
    val = getattr(Config, key.upper(), None)
    if val is not None:
        return str(val)
    return default

# 3. Initialize Supabase Client
@st.cache_resource
def get_supabase_client() -> Client:
    url = get_config("SUPABASE_URL")
    key = get_config("SUPABASE_KEY")
    if not url or url == "YOUR_SUPABASE_URL" or not key or key == "YOUR_SUPABASE_SERVICE_ROLE_KEY":
        st.warning("⚠️ Supabase credentials are missing or set to defaults. Please check your config.")
        st.stop()
    return create_client(url, key)

def start_background_workers() -> bool:
    """
    Fires the background poller routine exactly once using a persistent execution gate
    so it runs headless in the background while the UI remains interactive.
    """
    try:
        from app.imou_poller import imou_poller
        from app.telegram_service import telegram_bot_poller
        
        imou_poller.start()
        telegram_bot_poller.start()
        return True
    except Exception as e:
        return False

# Start background monitoring loops headless exactly once
start_background_workers()

try:
    supabase = get_supabase_client()
except Exception as e:
    st.error(f"Failed to connect to Supabase: {str(e)}")
    st.stop()

# 4. Authentication Session Management
if "user" not in st.session_state:
    st.session_state["user"] = None
if "session_token" not in st.session_state:
    st.session_state["session_token"] = None

def handle_logout():
    try:
        supabase.auth.sign_out()
    except Exception:
        pass
    st.session_state["user"] = None
    st.session_state["session_token"] = None
    st.rerun()

# Render Login screen if user is not authenticated
if st.session_state["user"] is None:
    st.markdown("<h1 style='text-align: center; margin-top: 50px;'>🛡️ Imou-Exotel Monitoring Portal</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #9CA3AF;'>Authorized personnel security checkpoint</p>", unsafe_allow_html=True)
    
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
                    st.error("Please provide both email and password credentials.")
                else:
                    with st.spinner("Verifying credentials with database..."):
                        try:
                            auth_response = supabase.auth.sign_in_with_password({
                                "email": email,
                                "password": password
                            })
                            if auth_response.user and auth_response.session:
                                st.session_state["user"] = auth_response.user
                                st.session_state["session_token"] = auth_response.session.access_token
                                st.success("Access Granted! Loading system parameters...")
                                st.rerun()
                            else:
                                st.error("Authentication failed. Access Denied.")
                        except Exception as e:
                            st.error(f"Login process failed: {str(e)}")
    st.stop()

# 5. Render Main Dashboard Panel if session token is valid
st.sidebar.markdown("### 👤 User Information")
st.sidebar.write(f"Logged in as: **{st.session_state['user'].email}**")
st.sidebar.button("🔐 Terminate Session (Sign Out)", on_click=handle_logout, use_container_width=True)

st.sidebar.write("---")
st.sidebar.markdown("### ⚙️ System Metadata")
st.sidebar.markdown(f"**Target Device:** `{get_config('IMOU_DEVICE_ID', 'Unconfigured')}`")
st.sidebar.markdown(f"**Poll Interval:** `{get_config('IMOU_POLL_INTERVAL_SECONDS', '600')}s`")

# Dashboard Content Header
st.title("📊 Security & Notification Monitor Dashboard")
st.write("Real-time telemetry and control panel interface for Imou-Exotel-Telegram services.")
st.write("---")

# Query current is_paused state from database
try:
    state_res = supabase.table("system_state").select("is_paused").eq("id", 1).execute()
    if state_res.data:
        db_paused = state_res.data[0]["is_paused"]
    else:
        # Auto-seed initial system state if missing in the database
        supabase.table("system_state").insert({"id": 1, "is_paused": False}).execute()
        db_paused = False
except Exception as e:
    st.error(f"Error reading status from database: {str(e)}")
    db_paused = False

# Layout Structure: Left Column (Controls & State), Right Column (Metrics & Graphs)
left_col, right_col = st.columns([1, 2], gap="large")

with left_col:
    st.subheader("🛠️ Control panel")
    
    # Render Master pause switch
    new_paused = st.toggle(
        "⏸️ Pause / Resume All Activities", 
        value=db_paused, 
        help="Updates state directly inside Supabase. Background polling agent immediately honors this state.",
        key="master_pause_switch"
    )
    
    # If the user toggles the switch, push state directly to database
    if new_paused != db_paused:
        with st.spinner("Pusing update to database..."):
            try:
                supabase.table("system_state").update({"is_paused": new_paused}).eq("id", 1).execute()
                st.toast(f"System status successfully updated to: {'PAUSED ⛔' if new_paused else 'RUNNING ✅'}")
                st.rerun()
            except Exception as e:
                st.error(f"Failed to update database row: {str(e)}")

    st.write("")
    st.write("---")
    st.markdown("#### ℹ️ System Operational Status")
    if db_paused:
        st.error("⛔ **MONITORING IS CURRENTLY PAUSED**: All automated Exotel calls and Telegram notifications are suppressed until monitoring is reactivated.")
    else:
        st.success("✅ **SYSTEM ACTIVE**: Background threads are polling camera feeds and will automatically trigger telephone and message alerts upon offline states.")

with right_col:
    st.subheader("📈 System Telemetry Metrics")
    
    # Fetch offline events logs from the database
    try:
        logs_query = supabase.table("camera_logs").select("*").order("created_at", desc=True).limit(100).execute()
        logs_data = logs_query.data or []
    except Exception as e:
        st.error(f"Error loading logs telemetry: {str(e)}")
        logs_data = []

    # Display indicators using Streamlit columns
    total_alerts = len(logs_data)
    
    m_col1, m_col2 = st.columns(2)
    with m_col1:
        if db_paused:
            st.metric("Monitoring State", "PAUSED", delta="System Sleeping", delta_color="inverse")
        else:
            st.metric("Monitoring State", "ACTIVE", delta="System Tracking", delta_color="normal")
    with m_col2:
        st.metric("Recorded Alert Records (Last 100)", total_alerts, delta="-0 (Offline events)", delta_color="off")

st.write("")
    
    # Graph Visualization with Plotly
    if logs_data:
        df = pd.DataFrame(logs_data)
        df["created_at"] = pd.to_datetime(df["created_at"])
        df["date"] = df["created_at"].dt.date
        alert_counts = df.groupby("date").size().reset_index(name="Alerts Count")

        fig = px.bar(
            alert_counts,
            x="date",
            y="Alerts Count",
            title="Alert Occurrence History By Day",
            labels={"date": "Timeline Date", "Alerts Count": "Number of Alert Sequences"},
            template="plotly_dark",
            color_discrete_sequence=["#EF4444"]
        )
        fig.update_layout(height=260, margin=dict(l=20, r=20, t=40, b=20))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No recorded offline alerts found in Supabase logs.")

# 6. Detailed Telemetry Log Table
st.write("---")
st.subheader("📋 Telemetry logs history (Recent 100 Alert Cycles)")

if logs_data:
    df_logs = pd.DataFrame(logs_data)
    df_logs["created_at"] = pd.to_datetime(df_logs["created_at"])
    
    # Rename columns to match prompt specifications
    df_logs = df_logs.rename(columns={
        "device_id": "Device ID",
        "status": "Event Type",
        "created_at": "Time Stamp",
        "notification_sent": "Exotel/Telegram Dispatched"
    })
    
    st.dataframe(
        df_logs[["Device ID", "Event Type", "Time Stamp", "Exotel/Telegram Dispatched"]],
        column_config={
            "Time Stamp": st.column_config.DatetimeColumn("Time Stamp", format="YYYY-MM-DD HH:mm:ss"),
            "Exotel/Telegram Dispatched": st.column_config.CheckboxColumn("Exotel/Telegram Dispatched")
        },
        use_container_width=True,
        hide_index=True
    )

else:
    st.info("No logs are currently stored in the database.")

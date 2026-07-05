import sys
import os

# Ensure system path isolation so sub-modules in /app resolve seamlessly
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'app')))

import pandas as pd
import streamlit as st
import plotly.express as px
from supabase import create_client, Client

# Helper to format and localize ISO/UTC timestamps to IST string
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

# ==============================================================================
# 1. PAGE CONFIGISTRATION & DESIGN THEME
# ==============================================================================
st.set_page_config(
    page_title="Imou-Exotel Security Dashboard",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Dark Aesthetic Custom Styling overrides
st.markdown("""
<style>
    div[data-testid="stMetricValue"] {
        font-size: 2.2rem;
        font-weight: 700;
    }
    div[data-testid="stMetricDelta"] > div {
        font-size: 1rem;
    }
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
from app.supabase_service import get_frontend_client, get_backend_service_client

# Explicit Constants matching our Production Supabase SQL constraints
SYSTEM_STATE_UUID = "00000000-0000-0000-0000-000000000001"

def get_config(key: str, default: str = "") -> str:
    val = getattr(Config, key.upper(), None)
    if val is not None:
        return str(val)
    return default

# ==============================================================================
# 2. CLIENT SUBSTANTIATION & BACKGROUND DAEMONS
# ==============================================================================
@st.cache_resource
def get_supabase_client() -> Client:
    try:
        return get_backend_service_client()
    except Exception as e:
        st.warning(f"⚠️ Service role Supabase client initialization failed: {str(e)}")
        st.stop()

def start_background_workers() -> bool:
    """Fires background tracking engines inside standalone daemon threads exactly once."""
    try:
        from app.imou_poller import imou_poller
        from app.telegram_service import telegram_bot_poller
        
        imou_poller.start()
        telegram_bot_poller.start()
        return True
    except Exception:
        return False

# Initialize Background Routines
start_background_workers()

try:
    supabase = get_supabase_client()
except Exception as e:
    st.error(f"Failed to connect to Supabase Service Key Client: {str(e)}")
    st.stop()

auth_supabase = None
try:
    auth_supabase = get_frontend_client()
except Exception as e:
    st.error(f"Failed to initialize public Anon Supabase auth client: {str(e)}")

# ==============================================================================
# 3. AUTHENTICATION CONTROLS
# ==============================================================================
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

# Enforce secure login wall
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
                            if auth_supabase is None:
                                raise Exception("Public Anon Supabase auth client is uninitialized. Verify your variables.")
                            
                            auth_response = auth_supabase.auth.sign_in_with_password({
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
                            error_msg = str(e)
                            st.error(f"Login process failed: {error_msg}")
                            
                            if "Invalid login credentials" in error_msg:
                                st.info(
                                    "💡 **Troubleshooting Tip:** If you are sure your password is correct, "
                                    "verify that **Confirm Email** is disabled in your Supabase configuration panel "
                                    "(Authentication -> Providers -> Email -> Confirm Email) or that your manually created user is auto-confirmed."
                                )
    st.stop()

# ==============================================================================
# 4. ADMIN USER INTERFACE SIDEBAR PANEL
# ==============================================================================
st.sidebar.markdown("### 👤 User Information")
st.sidebar.write(f"Logged in as: **{st.session_state['user'].email}**")
st.sidebar.button("🔐 Terminate Session (Sign Out)", on_click=handle_logout, use_container_width=True)

st.sidebar.write("---")
st.sidebar.markdown("### ⚙️ System Metadata")
st.sidebar.markdown(f"**Target Device:** `{get_config('IMOU_DEVICE_ID', 'Unconfigured')}`")
st.sidebar.markdown(f"**Poll Interval:** `{get_config('IMOU_POLL_INTERVAL_SECONDS', '600')}s`")

st.title("📊 Security & Notification Monitor Dashboard")
st.write("Real-time telemetry and control panel interface for Imou-Exotel-Telegram services.")
st.write("---")

# Read state with true explicit UUID parsing to eradicate Postgres 22P02 casting failures
try:
    state_res = supabase.table("system_state").select("is_paused").eq("id", SYSTEM_STATE_UUID).execute()
    if state_res.data:
        db_paused = state_res.data[0]["is_paused"]
    else:
        # Auto-seed initial structural configuration row if not present
        supabase.table("system_state").insert({"id": SYSTEM_STATE_UUID, "is_paused": False}).execute()
        db_paused = False
except Exception as e:
    st.error(f"Error reading status from database: {str(e)}")
    db_paused = False

# Layout Structure: Split Grid
left_col, right_col = st.columns([1, 2], gap="large")

with left_col:
    st.subheader("🛠️ Control Panel")
    
    new_paused = st.toggle(
        "⏸️ Pause / Resume All Activities", 
        value=db_paused, 
        help="Updates state directly inside Supabase. Background polling agent immediately honors this state.",
        key="master_pause_switch"
    )
    
    # Update mutation block syncing state back to Supabase
    if new_paused != db_paused:
        with st.spinner("Pushing update to database..."):
            try:
                supabase.table("system_state").update({"is_paused": new_paused}).eq("id", SYSTEM_STATE_UUID).execute()
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

# ==============================================================================
# 5. LIVE METRICS & PLOTLY TIME HISTORY PLOT
# ==============================================================================
with right_col:
    st.subheader("📈 System Telemetry Metrics")
    
    # Query database sorting by production timestamp column (triggered_at) to avoid 42703 faults
    try:
        logs_query = supabase.table("camera_logs").select("*").order("triggered_at", desc=True).limit(100).execute()
        logs_data = logs_query.data or []
    except Exception as e:
        st.error(f"Error loading logs telemetry: {str(e)}")
        logs_data = []

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
    
    # Render Plotly visual graphing frame
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

# ==============================================================================
# 6.INTERACTIVE HISTORICAL LOGGER DATA TABLE
# ==============================================================================
st.write("---")
st.subheader("📋 Telemetry Logs History (Recent 100 Alert Cycles)")

if logs_data:
    df_logs = pd.DataFrame(logs_data)
    
    # Format and convert the timestamp column explicitly to IST string representation
    df_logs["Time Stamp"] = df_logs["triggered_at"].apply(format_to_ist_str)
    
    # Map the dispatch notification checkboxes by combining the Exotel & Telegram states
    exotel_col = df_logs["exotel_call_triggered"].fillna(False) if "exotel_call_triggered" in df_logs.columns else False
    telegram_col = df_logs["telegram_alert_sent"].fillna(False) if "telegram_alert_sent" in df_logs.columns else False
    df_logs["Exotel/Telegram Dispatched"] = exotel_col | telegram_col
    
    # Clean up column structure display schemas
    df_logs = df_logs.rename(columns={
        "device_id": "Device ID",
        "event_type": "Event Type"
    })
    
    st.dataframe(
        df_logs[["Device ID", "Event Type", "Time Stamp", "Exotel/Telegram Dispatched"]],
        column_config={
            "Time Stamp": st.column_config.TextColumn("Time Stamp"),
            "Exotel/Telegram Dispatched": st.column_config.CheckboxColumn("Exotel/Telegram Dispatched")
        },
        use_container_width=True,
        hide_index=True
    )
else:
    st.info("No logs are currently stored in the database.")
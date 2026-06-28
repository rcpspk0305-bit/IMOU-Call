# Imou Camera Status Monitor & Exotel Voice Call Agent

A production-grade Python Flask application engineered for API protection, rate optimization, live Telegram control plane management, and absolute operational control. Monitors Imou camera status through both real-time webhooks and active background polling, triggering automated voice calls via Exotel when cameras drop offline.

---

## 🌟 Telegram Bot Control Plane & Features

1. **Telegram Control Plane (`app/telegram_service.py`)**:
   - Long-polling background daemon listening for commands restricted strictly to `TELEGRAM_ALLOWED_CHAT_ID`.
   - **`/pause`**: Switches runtime state to `is_paused = True`. Logs `"Monitoring is currently paused. Skipping cycle."` and disables Exotel alerts.
   - **`/resume`**: Switches `is_paused = False` and resumes active background tracking.
   - **`/status`**: Returns real-time system state (Active/Paused, last Imou API check timestamp, and last Exotel dial timestamp).
   - **`/checknow`**: Forces an instant, standalone request to Imou API to check camera state right now and reports the result back to Telegram!
   - **`/stop`**: Safely toggles lifecycle flags to gracefully terminate monitoring loops and process execution.
2. **Immediate Digital Alert Upgrade**:
   - Whenever a camera is confirmed offline, an immediate digital text notification is sent to Telegram alongside the Exotel phone call routine!
3. **Agent Lockout (`last_call_timestamp`)**: Thread-safe lockout manager tracking Exotel API executions to verify at least 30 minutes (`EXOTEL_CALL_LOCKOUT_SECONDS=1800`) have elapsed before placing another voice call for a device.
4. **Optimized Polling Rate (10-15 Minutes)**: Background polling routine hits the Imou gateway once every 10 minutes (`IMOU_POLL_INTERVAL_SECONDS=600`).

---

## 🚀 Getting Started

### 1. Installation & Setup
```bash
cd C:\Users\rc821\imou-exotel-agent
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Configuration (.env)
```env
# Exotel Credentials & Lockout (30 minutes = 1800s)
EXOTEL_SUBDOMAIN=api.in.exotel.com
EXOTEL_SID=YOUR_EXOTEL_ACCOUNT_SID
EXOTEL_KEY=YOUR_EXOTEL_API_KEY
EXOTEL_TOKEN=YOUR_EXOTEL_API_TOKEN
FROM_NUMBER=YOUR_PERSONAL_VERIFIED_MOBILE
CALLER_ID=YOUR_EXOPHONE_VIRTUAL_NUMBER
APP_ID=YOUR_EXOTEL_APP_ID
EXOTEL_CALL_LOCKOUT_SECONDS=1800

# Imou Credentials & Polling Interval (10 minutes = 600s)
IMOU_APP_ID=YOUR_IMOU_APP_ID
IMOU_APP_SECRET=YOUR_IMOU_APP_SECRET
IMOU_DEVICE_ID=YOUR_IMOU_DEVICE_ID
IMOU_POLL_INTERVAL_SECONDS=600
IMOU_API_BASE_URL=https://openapi.easy4ip.com/openapi

# Telegram Bot Control Plane Credentials
TELEGRAM_BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
TELEGRAM_ALLOWED_CHAT_ID=YOUR_TELEGRAM_ALLOWED_CHAT_ID

# App Settings
BUFFER_DELAY_SECONDS=180
PORT=5000
```

---

## 🏃 Running the Application

Start the application:
```bash
python run.py
```

---

## 🧪 Testing

Run automated tests:
```bash
pytest -v
```

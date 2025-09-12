import os
import requests
import psycopg2
from datetime import datetime, timedelta
from fastapi import Request
from fastapi.responses import RedirectResponse, HTMLResponse

# ------------------- Environment Variables -------------------
MS_CLIENT_ID = os.getenv("MS_CLIENT_ID")
MS_CLIENT_SECRET = os.getenv("MS_CLIENT_SECRET")
MS_REDIRECT_URI = os.getenv("MS_REDIRECT_URI")  # e.g., https://your-app.onrender.com/ms/callback
MS_TENANT_ID = os.getenv("MS_TENANT_ID", "common")  # use "common" for multi-tenant apps
DATABASE_URL = os.getenv("DATABASE_URL")  # PostgreSQL URL from Render or elsewhere

AUTH_URL = f"https://login.microsoftonline.com/{MS_TENANT_ID}/oauth2/v2.0/authorize"
TOKEN_URL = f"https://login.microsoftonline.com/{MS_TENANT_ID}/oauth2/v2.0/token"

# ------------------- PostgreSQL Connection -------------------
def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def initialize_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ms_tokens (
            user_id TEXT PRIMARY KEY,
            access_token TEXT NOT NULL,
            refresh_token TEXT,
            expiry_time TIMESTAMP
        )
    """)
    conn.commit()
    cur.close()
    conn.close()

initialize_db()

# ------------------- Utility -------------------
def normalize_user_id(user_id: str) -> str:
    if not user_id:
        return "default_user"
    return user_id.replace("@s.whatsapp.net", "").replace("+", "").strip()

# ------------------- Database Helpers -------------------
def save_token(user_id: str, access_token: str, refresh_token=None, expiry_time=None):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO ms_tokens (user_id, access_token, refresh_token, expiry_time)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (user_id) 
        DO UPDATE SET access_token = EXCLUDED.access_token, 
                      refresh_token = EXCLUDED.refresh_token,
                      expiry_time = EXCLUDED.expiry_time
    """, (user_id, access_token, refresh_token, expiry_time))
    conn.commit()
    cur.close()
    conn.close()

def get_token(user_id: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT access_token FROM ms_tokens WHERE user_id=%s", (user_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row:
        return row[0]
    return None

# ------------------- OAuth Login URL -------------------
def get_ms_login_url(user_id: str):
    user_id = normalize_user_id(user_id)
    scope = "User.Read OnlineMeetings.ReadWrite"
    return (
        f"{AUTH_URL}?client_id={MS_CLIENT_ID}"
        f"&response_type=code"
        f"&redirect_uri={MS_REDIRECT_URI}"
        f"&response_mode=query"
        f"&scope={scope}"
        f"&state={user_id}"
    )

# ------------------- OAuth Routes -------------------
async def ms_login(user_id: str):
    user_id = normalize_user_id(user_id)
    return RedirectResponse(url=get_ms_login_url(user_id))

async def ms_callback(request: Request):
    code = request.query_params.get("code")
    user_id = normalize_user_id(request.query_params.get("state"))

    if not code:
        return HTMLResponse("<h3>❌ No code returned from Microsoft</h3>")

    data = {
        "client_id": MS_CLIENT_ID,
        "client_secret": MS_CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": MS_REDIRECT_URI,
        "scope": "User.Read OnlineMeetings.ReadWrite"
    }

    response = requests.post(TOKEN_URL, data=data)
    token_json = response.json()

    if "access_token" not in token_json:
        return HTMLResponse(f"<h3>❌ Failed to authenticate: {token_json}</h3>")

    access_token = token_json["access_token"]
    refresh_token = token_json.get("refresh_token")
    expiry_time = datetime.utcnow() + timedelta(seconds=token_json.get("expires_in", 3600))

    # Save token in database
    save_token(user_id, access_token, refresh_token, expiry_time)

    return HTMLResponse(
        f"<h2>✅ Microsoft login successful!</h2>"
        f"<p>You can now go back to WhatsApp and type <b>teams</b> again to continue.</p>"
    )

# ------------------- Teams Meeting Creation -------------------
def create_teams_meeting(user_id: str, subject: str, start_time: str, duration_minutes: int = 30):
    user_id = normalize_user_id(user_id)

    access_token = get_token(user_id)
    if not access_token:
        raise Exception("User not logged in with Microsoft Teams. Please authenticate first.")

    url = "https://graph.microsoft.com/v1.0/me/onlineMeetings"

    start_dt = datetime.strptime(start_time, "%Y-%m-%dT%H:%M:%SZ")
    end_dt = start_dt + timedelta(minutes=duration_minutes)

    body = {
        "startDateTime": start_dt.isoformat() + "Z",
        "endDateTime": end_dt.isoformat() + "Z",
        "subject": subject
    }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    response = requests.post(url, headers=headers, json=body)
    if response.status_code in (200, 201):
        return response.json().get("joinWebUrl")
    else:
        raise Exception(f"Failed to create Teams meeting: {response.text}")







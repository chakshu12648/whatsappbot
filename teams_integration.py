import os
import requests
from datetime import datetime, timedelta
from fastapi import Request
from fastapi.responses import RedirectResponse, HTMLResponse
from pymongo import MongoClient, errors
import certifi

from app import user_sessions, handle_meeting_flow  # Import session storage & handler

# ------------------- Environment Variables -------------------
MS_CLIENT_ID = os.getenv("MS_CLIENT_ID")
MS_CLIENT_SECRET = os.getenv("MS_CLIENT_SECRET")
MS_REDIRECT_URI = os.getenv("MS_REDIRECT_URI")
MS_TENANT_ID = os.getenv("MS_TENANT_ID", "common")
MONGO_URL = os.getenv("MONGO_URL")

AUTH_URL = f"https://login.microsoftonline.com/{MS_TENANT_ID}/oauth2/v2.0/authorize"
TOKEN_URL = f"https://login.microsoftonline.com/{MS_TENANT_ID}/oauth2/v2.0/token"

# ------------------- MongoDB Setup -------------------
try:
    client = MongoClient(MONGO_URL, tls=True, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    db = client.get_database("whatsappbot")
    tokens_collection = db.ms_tokens
    print("✅ Connected to MongoDB")
except errors.ServerSelectionTimeoutError as e:
    print(f"❌ MongoDB connection failed: {e}")
    tokens_collection = None

# ------------------- Utility -------------------
def normalize_user_id(user_id: str) -> str:
    if not user_id:
        return "default_user"
    return user_id.replace("@s.whatsapp.net", "").replace("+", "").strip()

# ------------------- Database Helpers -------------------
def save_token(user_id: str, access_token: str, refresh_token=None, expiry_time=None):
    if not tokens_collection:
        return
    tokens_collection.update_one(
        {"user_id": user_id},
        {"$set": {"access_token": access_token, "refresh_token": refresh_token, "expiry_time": expiry_time}},
        upsert=True
    )

def get_token(user_id: str):
    if not tokens_collection:
        return None
    doc = tokens_collection.find_one({"user_id": user_id})
    if not doc:
        return None

    access_token = doc.get("access_token")
    refresh_token = doc.get("refresh_token")
    expiry_time = doc.get("expiry_time")

    # Refresh if expired
    if expiry_time and datetime.utcnow() >= expiry_time:
        data = {
            "client_id": MS_CLIENT_ID,
            "client_secret": MS_CLIENT_SECRET,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
            "redirect_uri": MS_REDIRECT_URI,
        }
        response = requests.post(TOKEN_URL, data=data)
        token_json = response.json()
        if "access_token" not in token_json:
            return None
        new_access_token = token_json["access_token"]
        new_refresh_token = token_json.get("refresh_token", refresh_token)
        new_expiry = datetime.utcnow() + timedelta(seconds=token_json.get("expires_in", 3600))
        save_token(user_id, new_access_token, new_refresh_token, new_expiry)
        return new_access_token

    return access_token

# ------------------- OAuth Login URL -------------------
def get_ms_login_url(user_id: str):
    user_id = normalize_user_id(user_id)
    scope = "User.Read OnlineMeetings.ReadWrite offline_access"
    url = (
        f"{AUTH_URL}?client_id={MS_CLIENT_ID}"
        f"&response_type=code"
        f"&redirect_uri={MS_REDIRECT_URI}"
        f"&response_mode=query"
        f"&scope={scope}"
        f"&state={user_id}"
    )
    return url

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
        "scope": "User.Read OnlineMeetings.ReadWrite offline_access"
    }

    response = requests.post(TOKEN_URL, data=data)
    token_json = response.json()
    if "access_token" not in token_json:
        return HTMLResponse(f"<h3>❌ Failed to authenticate: {token_json}</h3>")

    access_token = token_json["access_token"]
    refresh_token = token_json.get("refresh_token")
    expiry_time = datetime.utcnow() + timedelta(seconds=token_json.get("expires_in", 3600))

    save_token(user_id, access_token, refresh_token, expiry_time)

    # Automatically continue Teams flow if session exists
    if user_id in user_sessions and user_sessions[user_id].get("platform") == "teams":
        session = user_sessions[user_id]
        if session["step"] == "topic":
            message = "✅ You are now authenticated with Microsoft Teams! What’s the meeting topic?"
            reply = handle_meeting_flow(user_id, message)
            return HTMLResponse(f"<h3>{reply}</h3>")

    return HTMLResponse("<h3>✅ Microsoft login successful! You can now go back to WhatsApp to continue your Teams meeting creation.</h3>")

# ------------------- Teams Meeting Creation -------------------
def create_teams_meeting(user_id: str, subject: str, start_time: str, duration_minutes: int = 30):
    user_id = normalize_user_id(user_id)
    access_token = get_token(user_id)
    if not access_token:
        raise Exception("User not logged in with Microsoft Teams. Please authenticate first.")

    url = "https://graph.microsoft.com/v1.0/me/onlineMeetings"
    start_dt = datetime.strptime(start_time, "%Y-%m-%dT%H:%M:%SZ")
    end_dt = start_dt + timedelta(minutes=duration_minutes)
    body = {"startDateTime": start_dt.isoformat() + "Z",
            "endDateTime": end_dt.isoformat() + "Z",
            "subject": subject}
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    response = requests.post(url, headers=headers, json=body)
    if response.status_code in (200, 201):
        return response.json().get("joinWebUrl")
    else:
        raise Exception(f"Failed to create Teams meeting: {response.text}")











import os
import requests
import json
from fastapi.responses import RedirectResponse, PlainTextResponse
from datetime import datetime, timedelta
from pymongo import MongoClient

# ------------------- MongoDB Connection -------------------
MONGO_URL = os.getenv("MONGO_URL", "")
print(f"🔌 Connecting to MongoDB at: {MONGO_URL}")

client = MongoClient(MONGO_URL, tls=True, tlsAllowInvalidCertificates=True)
db = client["whatsappbot"]   # database
tokens_collection = db["ms_tokens"]  # collection

print("✅ MongoDB connected, using DB: whatsappbot, Collection: ms_tokens")

# ------------------- Microsoft OAuth Config -------------------
MS_CLIENT_ID = os.getenv("MS_CLIENT_ID")
MS_CLIENT_SECRET = os.getenv("MS_CLIENT_SECRET")
MS_TENANT_ID = os.getenv("MS_TENANT_ID")
APP_BASE_URL = os.getenv("APP_BASE_URL", "https://whatsappbot-f8mu.onrender.com")

AUTHORITY = f"https://login.microsoftonline.com/{MS_TENANT_ID}"
AUTHORIZE_URL = f"{AUTHORITY}/oauth2/v2.0/authorize"
TOKEN_URL = f"{AUTHORITY}/oauth2/v2.0/token"
SCOPES = ["offline_access", "Calendars.ReadWrite", "User.Read"]

# ------------------- Helpers -------------------
def normalize_user_id(user_id: str) -> str:
    """Normalize user ID (phone numbers become consistent)."""
    return str(user_id).replace("whatsapp:", "").strip()

def save_token(user_id: str, token_data: dict):
    """Save or update token in MongoDB."""
    user_id = normalize_user_id(user_id)
    print(f"💾 Saving token for {user_id}")
    token_data["expires_at"] = (
        datetime.utcnow() + timedelta(seconds=token_data["expires_in"])
    ).isoformat()
    tokens_collection.update_one({"user_id": user_id}, {"$set": token_data}, upsert=True)
    print(f"✅ Token saved for {user_id}")

def get_token(user_id: str):
    """Retrieve a valid token, refresh if expired."""
    user_id = normalize_user_id(user_id)
    token = tokens_collection.find_one({"user_id": user_id})

    if not token:
        print(f"⚠️ No token found for {user_id}")
        return None

    expires_at = datetime.fromisoformat(token["expires_at"])
    if expires_at > datetime.utcnow():
        print(f"✅ Valid token found for {user_id}")
        return token["access_token"]

    print(f"🔄 Token expired for {user_id}, refreshing...")
    refresh_token = token["refresh_token"]
    data = {
        "client_id": MS_CLIENT_ID,
        "client_secret": MS_CLIENT_SECRET,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "scope": " ".join(SCOPES),
    }
    response = requests.post(TOKEN_URL, data=data)
    if response.status_code == 200:
        new_token = response.json()
        new_token["user_id"] = user_id
        save_token(user_id, new_token)
        print(f"✅ Token refreshed for {user_id}")
        return new_token["access_token"]
    else:
        print(f"❌ Failed to refresh token for {user_id}: {response.text}")
        return None

# ------------------- Routes -------------------
async def ms_login(user_id: str):
    """Generate Microsoft login URL."""
    user_id = normalize_user_id(user_id)
    print(f"🔑 MS Login requested for {user_id}")
    redirect_uri = f"{APP_BASE_URL}/ms/callback"
    auth_url = (
        f"{AUTHORIZE_URL}?client_id={MS_CLIENT_ID}"
        f"&response_type=code&redirect_uri={redirect_uri}"
        f"&response_mode=query&scope={' '.join(SCOPES)}&state={user_id}"
    )
    return RedirectResponse(auth_url)

async def ms_callback(request):
    """Handle Microsoft OAuth callback."""
    params = dict(request.query_params)
    code = params.get("code")
    user_id = params.get("state")

    if not code or not user_id:
        print("❌ MS callback missing code or user_id")
        return PlainTextResponse("❌ Missing code or user_id", status_code=400)

    redirect_uri = f"{APP_BASE_URL}/ms/callback"
    data = {
        "client_id": MS_CLIENT_ID,
        "client_secret": MS_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "scope": " ".join(SCOPES),
    }

    print(f"📥 Exchanging code for token for {user_id}")
    response = requests.post(TOKEN_URL, data=data)
    if response.status_code == 200:
        token_data = response.json()
        token_data["user_id"] = normalize_user_id(user_id)
        save_token(user_id, token_data)
        return PlainTextResponse("✅ Microsoft Teams login successful! You can return to WhatsApp.")
    else:
        print(f"❌ Token exchange failed: {response.text}")
        return PlainTextResponse("❌ Microsoft Teams login failed", status_code=400)

# ------------------- Meeting Creation -------------------
def create_teams_meeting(user_id: str, topic: str, start_time: str, duration: int):
    """Create a Teams meeting using Microsoft Graph API."""
    access_token = get_token(user_id)
    if not access_token:
        raise Exception("No valid token available. Please login again.")

    url = "https://graph.microsoft.com/v1.0/me/onlineMeetings"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

    start_dt = datetime.strptime(start_time, "%Y-%m-%dT%H:%M:%SZ")
    end_dt = start_dt + timedelta(minutes=duration)

    meeting_data = {
        "subject": topic,
        "startDateTime": start_dt.isoformat() + "Z",
        "endDateTime": end_dt.isoformat() + "Z",
    }

    print(f"📤 Creating Teams meeting for {user_id}: {topic} at {start_time}")
    response = requests.post(url, headers=headers, json=meeting_data)
    if response.status_code == 201:
        link = response.json().get("joinWebUrl")
        print(f"✅ Teams meeting created for {user_id}: {link}")
        return link
    else:
        print(f"❌ Failed to create Teams meeting: {response.text}")
        raise Exception(response.text)









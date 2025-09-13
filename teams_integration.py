import os
import requests
from datetime import datetime, timedelta
from fastapi import Request
from fastapi.responses import RedirectResponse, HTMLResponse
from pymongo import MongoClient, errors
import certifi

# ------------------- Environment Variables -------------------
MS_CLIENT_ID = os.getenv("MS_CLIENT_ID")
MS_CLIENT_SECRET = os.getenv("MS_CLIENT_SECRET")
MS_REDIRECT_URI = os.getenv("MS_REDIRECT_URI")
MS_TENANT_ID = os.getenv("MS_TENANT_ID", "common")  # multi-tenant apps
MONGO_URL = os.getenv("MONGO_URL")  # MongoDB connection string

AUTH_URL = f"https://login.microsoftonline.com/{MS_TENANT_ID}/oauth2/v2.0/authorize"
TOKEN_URL = f"https://login.microsoftonline.com/{MS_TENANT_ID}/oauth2/v2.0/token"

# ------------------- MongoDB Setup -------------------
print(f"📡 Connecting to MongoDB at {MONGO_URL}")
try:
    client = MongoClient(
        MONGO_URL,
        tls=True,
        tlsCAFile=certifi.where(),
        serverSelectionTimeoutMS=5000
    )
    client.admin.command("ping")
    db = client.get_database("whatsappbot")
    tokens_collection = db.ms_tokens
    print("✅ Connected to MongoDB, using DB=whatsappbot, Collection=ms_tokens")
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
        print("❌ No MongoDB connection available to save token")
        return False
    user_id = normalize_user_id(user_id)
    try:
        result = tokens_collection.update_one(
            {"user_id": user_id},
            {"$set": {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expiry_time": expiry_time
            }},
            upsert=True
        )
        print(f"💾 Token saved for {user_id}, matched={result.matched_count}, modified={result.modified_count}")
        return True
    except Exception as e:
        print(f"❌ Failed to save token for {user_id}: {e}")
        return False

def get_token(user_id: str):
    if not tokens_collection:
        print("❌ No MongoDB connection available to fetch token")
        return None

    user_id = normalize_user_id(user_id)
    print(f"🔍 Fetching token for {user_id}")

    try:
        doc = tokens_collection.find_one({"user_id": user_id})
        print(f"📄 MongoDB returned: {doc}")
    except Exception as e:
        print(f"❌ Error fetching token for {user_id}: {e}")
        return None

    if not doc:
        print(f"⚠️ No token found for {user_id}")
        return None

    access_token = doc.get("access_token")
    refresh_token = doc.get("refresh_token")
    expiry_time = doc.get("expiry_time")

    # Convert string to datetime if needed
    if isinstance(expiry_time, str):
        try:
            expiry_time = datetime.fromisoformat(expiry_time)
        except Exception:
            expiry_time = None

    # Refresh if expired
    if expiry_time and datetime.utcnow() >= expiry_time:
        print(f"🔄 Token expired for {user_id}, refreshing...")
        data = {
            "client_id": MS_CLIENT_ID,
            "client_secret": MS_CLIENT_SECRET,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
            "redirect_uri": MS_REDIRECT_URI,
        }
        response = requests.post(TOKEN_URL, data=data)
        token_json = response.json()
        print(f"📥 Refresh response: {token_json}")

        if "access_token" not in token_json:
            print(f"❌ Refresh failed for {user_id}")
            return None

        new_access_token = token_json["access_token"]
        new_refresh_token = token_json.get("refresh_token", refresh_token)
        new_expiry = datetime.utcnow() + timedelta(seconds=token_json.get("expires_in", 3600))

        save_token(user_id, new_access_token, new_refresh_token, new_expiry)
        return new_access_token

    print(f"✅ Valid token found for {user_id}")
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
    print(f"🔗 Generated login URL for {user_id}: {url}")
    return url

# ------------------- OAuth Routes -------------------
async def ms_login(user_id: str):
    user_id = normalize_user_id(user_id)
    print(f"🔑 MS Login requested for {user_id}")
    return RedirectResponse(url=get_ms_login_url(user_id))

async def ms_callback(request: Request):
    code = request.query_params.get("code")
    user_id = normalize_user_id(request.query_params.get("state"))

    print(f"📥 Callback received for {user_id} with code={code}")

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
    print(f"📥 Token exchange response for {user_id}: {token_json}")

    if "access_token" not in token_json:
        return HTMLResponse(f"<h3>❌ Failed to authenticate: {token_json}</h3>")

    access_token = token_json["access_token"]
    refresh_token = token_json.get("refresh_token")
    expiry_time = datetime.utcnow() + timedelta(seconds=token_json.get("expires_in", 3600))

    # Save token reliably
    save_token(user_id, access_token, refresh_token, expiry_time)

    return HTMLResponse(
        f"<h2>✅ Microsoft login successful!</h2>"
        f"<p>You can now go back to WhatsApp and type <b>teams</b> again to continue.</p>"
    )

# ------------------- Teams Meeting Creation -------------------
def create_teams_meeting(user_id: str, subject: str, start_time: str, duration_minutes: int = 30):
    user_id = normalize_user_id(user_id)
    print(f"📅 Creating Teams meeting for {user_id}")

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

    print(f"📤 Sending request to Graph API for {user_id}: {body}")
    response = requests.post(url, headers=headers, json=body)
    print(f"📥 Graph API response for {user_id}: {response.status_code} {response.text}")

    if response.status_code in (200, 201):
        link = response.json().get("joinWebUrl")
        print(f"✅ Teams meeting created for {user_id}: {link}")
        return link
    else:
        raise Exception(f"Failed to create Teams meeting: {response.text}")











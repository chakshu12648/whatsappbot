import os
import requests
from datetime import datetime, timedelta
from fastapi import Request
from fastapi.responses import RedirectResponse

# ------------------- Environment Variables -------------------
MS_CLIENT_ID = os.getenv("MS_CLIENT_ID")
MS_CLIENT_SECRET = os.getenv("MS_CLIENT_SECRET")
MS_REDIRECT_URI = os.getenv("MS_REDIRECT_URI")  # e.g., https://your-app.onrender.com/ms/callback
MS_TENANT_ID = os.getenv("MS_TENANT_ID", "common")  # use "common" for multi-tenant

AUTH_URL = f"https://login.microsoftonline.com/{MS_TENANT_ID}/oauth2/v2.0/authorize"
TOKEN_URL = f"https://login.microsoftonline.com/{MS_TENANT_ID}/oauth2/v2.0/token"

# ------------------- In-memory storage -------------------
teams_sessions = {}  # Stores user_id -> access_token

# ------------------- OAuth Login URL -------------------
def get_ms_login_url(user_id: str):
    """Generate login URL and pass user_id in state"""
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
    """Redirect user to Microsoft login"""
    return RedirectResponse(url=get_ms_login_url(user_id))

async def ms_callback(request: Request):
    """Handle OAuth callback and exchange code for token"""
    code = request.query_params.get("code")
    state = request.query_params.get("state")  # user_id from login

    if not code:
        return {"error": "No code returned"}

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
        return {"error": token_json}

    access_token = token_json["access_token"]

    # Store access token for this user
    if state:
        teams_sessions[state] = access_token
        return {"message": "Microsoft login successful ✅"}
    else:
        return {"message": "Microsoft login successful ✅", "access_token": access_token}

# ------------------- Teams Meeting Creation -------------------
def create_teams_meeting(user_id: str, subject: str, start_time: str, duration_minutes: int = 30):
    """Create a Teams meeting using Microsoft Graph API"""
    if user_id not in teams_sessions:
        raise Exception("User not logged in with Microsoft Teams. Please login first.")

    access_token = teams_sessions[user_id]
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
    if response.status_code == 201:
        return response.json().get("joinWebUrl")
    else:
        raise Exception(f"Failed to create Teams meeting: {response.text}")


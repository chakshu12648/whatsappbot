import os
import requests
from datetime import datetime, timedelta
from fastapi import Request
from fastapi.responses import RedirectResponse

# Load environment variables
MS_CLIENT_ID = os.getenv("MS_CLIENT_ID")
MS_CLIENT_SECRET = os.getenv("MS_CLIENT_SECRET")
MS_REDIRECT_URI = os.getenv("MS_REDIRECT_URI")  # e.g. https://your-app.onrender.com/ms/callback
MS_TENANT_ID = os.getenv("MS_TENANT_ID", "common")  # use "common" for multi-tenant

AUTH_URL = f"https://login.microsoftonline.com/{MS_TENANT_ID}/oauth2/v2.0/authorize"
TOKEN_URL = f"https://login.microsoftonline.com/{MS_TENANT_ID}/oauth2/v2.0/token"

# ------------------- OAuth Routes -------------------

def get_ms_login_url():
    scope = "User.Read OnlineMeetings.ReadWrite"
    return (
        f"{AUTH_URL}?client_id={MS_CLIENT_ID}"
        f"&response_type=code"
        f"&redirect_uri={MS_REDIRECT_URI}"
        f"&response_mode=query"
        f"&scope={scope}"
    )

async def ms_login():
    """Redirect user to Microsoft login"""
    return RedirectResponse(url=get_ms_login_url())

async def ms_callback(request: Request):
    """Handle OAuth callback and exchange code for token"""
    code = request.query_params.get("code")
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

    # Save token in memory (for demo). In production, save securely.
    access_token = token_json["access_token"]
    return {"message": "Microsoft login successful ✅", "access_token": access_token}

# ------------------- Teams Meeting Creation -------------------

def create_teams_meeting(access_token, subject, start_time, duration_minutes=30):
    """Create a Teams meeting using Microsoft Graph API"""
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

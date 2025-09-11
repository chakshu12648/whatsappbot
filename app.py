print("Starting app...")

import os
import requests
import base64
from datetime import datetime, timedelta
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from fastapi.responses import Response
from twilio.twiml.messaging_response import MessagingResponse
from google.oauth2 import service_account
from googleapiclient.discovery import build

app = FastAPI()
@app.get("/")
async def root():
    return PlainTextResponse("🚀 WhatsApp Bot is running on Render!")

# ----------- ENVIRONMENT VARIABLES -----------
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")

ZOOM_CLIENT_ID = os.getenv("ZOOM_CLIENT_ID")
ZOOM_CLIENT_SECRET = os.getenv("ZOOM_CLIENT_SECRET")
ZOOM_ACCOUNT_ID = os.getenv("ZOOM_ACCOUNT_ID")

GOOGLE_SERVICE_ACCOUNT_FILE = "service_account.json"

# ----------- ZOOM FUNCTIONS -----------

def get_zoom_access_token():
    token_url = "https://zoom.us/oauth/token"
    auth_header = base64.b64encode(f"{ZOOM_CLIENT_ID}:{ZOOM_CLIENT_SECRET}".encode()).decode()

    headers = {
        "Authorization": f"Basic {auth_header}",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    data = {
        "grant_type": "account_credentials",
        "account_id": ZOOM_ACCOUNT_ID
    }

    response = requests.post(token_url, headers=headers, data=data)
    if response.status_code == 200:
        return response.json()["access_token"]
    else:
        raise Exception(f"Failed to get Zoom access token: {response.text}")

def create_zoom_meeting(topic, start_time, duration):
    access_token = get_zoom_access_token()
    meeting_url = "https://api.zoom.us/v2/users/me/meetings"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    meeting_data = {
        "topic": topic,
        "type": 2,
        "start_time": start_time,
        "duration": duration,
        "timezone": "UTC",
        "settings": {"host_video": True, "participant_video": True}
    }

    response = requests.post(meeting_url, headers=headers, json=meeting_data)
    if response.status_code == 201:
        return response.json()["join_url"]
    else:
        raise Exception(f"Failed to create Zoom meeting: {response.text}")

# ----------- GOOGLE MEET FUNCTIONS ----------

def create_google_meet(topic, start_time, duration):
    credentials = service_account.Credentials.from_service_account_file(
        GOOGLE_SERVICE_ACCOUNT_FILE,
        scopes=["https://www.googleapis.com/auth/calendar"]
    )
    service = build("calendar", "v3", credentials=credentials)

    start_dt = datetime.strptime(start_time, "%Y-%m-%dT%H:%M:%SZ")
    end_dt = start_dt + timedelta(minutes=duration)

    event = {
        "summary": topic,
        "start": {"dateTime": start_dt.isoformat() + "Z", "timeZone": "UTC"},
        "end": {"dateTime": end_dt.isoformat() + "Z", "timeZone": "UTC"},
        "conferenceData": {
            "createRequest": {
                "requestId": "meet123",
                "conferenceSolutionKey": {"type": "hangoutsMeet"}
            }
        }
    }

    created_event = service.events().insert(
        calendarId="primary",
        body=event,
        conferenceDataVersion=1
    ).execute()

    return created_event["hangoutLink"]

# ----------- FASTAPI ROUTE FOR WHATSAPP -----------

@app.post("/webhook", response_class=PlainTextResponse, response_model=None)
async def whatsapp_webhook(request: Request):
    form = await request.form()
    incoming_msg = form.get("Body", "").strip()
    resp = MessagingResponse()

    try:
        # Expected message format: Zoom|Topic|2025-09-06T15:00:00Z|30
        # Or Google|Topic|2025-09-06T15:00:00Z|30
        parts = incoming_msg.split("|")
        if len(parts) != 4:
            resp.message("⚠️ Format: Platform|Topic|StartTime(YYYY-MM-DDTHH:MM:SSZ)|Duration(mins)")
            return str(resp)

        platform, topic, start_time, duration = parts
        duration = int(duration)
        platform = platform.lower()

        if platform == "zoom":
            link = create_zoom_meeting(topic, start_time, duration)
        elif platform == "google":
            link = create_google_meet(topic, start_time, duration)
        else:
            resp.message("❌ Platform must be 'Zoom' or 'Google'")
            return str(resp)

        resp.message(f"✅ {platform.capitalize()} meeting created!\nJoin here: {link}")

    except Exception as e:
        resp.message(f"❌ Error: {str(e)}")

    return Response(content=str(resp), media_type="application/xml")

# ----------- START SERVER WITH UVICORN -----------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)




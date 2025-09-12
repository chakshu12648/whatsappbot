print("Starting app...")

import os
import requests
import base64
import json
from datetime import datetime, timedelta
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, Response
from twilio.twiml.messaging_response import MessagingResponse
from google.oauth2 import service_account
from googleapiclient.discovery import build
import dateparser

from teams_integration import ms_login, ms_callback, create_teams_meeting, teams_sessions

app = FastAPI()

# ------------------- Root -------------------
@app.get("/")
async def root():
    return PlainTextResponse("🚀 WhatsApp Bot is running on Render!")

# ------------------- MS OAuth Routes -------------------
@app.get("/ms/login")
async def login_to_ms(request: Request):
    # Use WhatsApp number as state
    user_id = request.query_params.get("user_id", "default_user")
    return await ms_login(user_id)

@app.get("/ms/callback")
async def callback_from_ms(request: Request):
    return await ms_callback(request)

# ------------------- ENVIRONMENT VARIABLES -------------------
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")

ZOOM_CLIENT_ID = os.getenv("ZOOM_CLIENT_ID")
ZOOM_CLIENT_SECRET = os.getenv("ZOOM_CLIENT_SECRET")
ZOOM_ACCOUNT_ID = os.getenv("ZOOM_ACCOUNT_ID")

# Load Google service account from environment variable
credentials_info = json.loads(os.environ["GOOGLE_CREDENTIALS"])
credentials_info["private_key"] = credentials_info["private_key"].replace("\\n", "\n")

google_credentials = service_account.Credentials.from_service_account_info(
    credentials_info,
    scopes=["https://www.googleapis.com/auth/calendar"]
)

# ------------------- ZOOM FUNCTIONS -------------------
def get_zoom_access_token():
    token_url = "https://zoom.us/oauth/token"
    auth_header = base64.b64encode(f"{ZOOM_CLIENT_ID}:{ZOOM_CLIENT_SECRET}".encode()).decode()
    headers = {"Authorization": f"Basic {auth_header}", "Content-Type": "application/x-www-form-urlencoded"}
    data = {"grant_type": "account_credentials", "account_id": ZOOM_ACCOUNT_ID}
    response = requests.post(token_url, headers=headers, data=data)
    if response.status_code == 200:
        return response.json()["access_token"]
    else:
        raise Exception(f"Failed to get Zoom access token: {response.text}")

def create_zoom_meeting(topic, start_time, duration):
    access_token = get_zoom_access_token()
    meeting_url = "https://api.zoom.us/v2/users/me/meetings"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    meeting_data = {
        "topic": topic,
        "type": 2,
        "start_time": start_time,
        "duration": duration,
        "timezone": "UTC",
        "settings": {
            "join_before_host": False,
            "waiting_room": False,
            "host_video": True,
            "participant_video": True,
            "mute_upon_entry": False
        }
    }
    response = requests.post(meeting_url, headers=headers, json=meeting_data)
    if response.status_code == 201:
        return response.json()["join_url"]
    else:
        raise Exception(f"Failed to create Zoom meeting: {response.text}")

# ------------------- GOOGLE MEET FUNCTIONS -------------------
def create_google_meet(topic, start_time, duration):
    service = build("calendar", "v3", credentials=google_credentials)
    start_dt = datetime.strptime(start_time, "%Y-%m-%dT%H:%M:%SZ")
    end_dt = start_dt + timedelta(minutes=duration)

    event = {
        "summary": topic,
        "start": {"dateTime": start_dt.isoformat() + "Z", "timeZone": "UTC"},
        "end": {"dateTime": end_dt.isoformat() + "Z", "timeZone": "UTC"},
    }

    created_event = service.events().insert(calendarId="primary", body=event).execute()
    meet_link = created_event.get("hangoutLink") or created_event.get("htmlLink")
    return meet_link

# ------------------- INTERACTIVE SESSION STORAGE -------------------
user_sessions = {}

def handle_meeting_flow(user_id, message):
    msg = message.lower()

    # Initialize session if not exists
    if user_id not in user_sessions:
        if "zoom" in msg:
            user_sessions[user_id] = {"platform": "zoom", "step": "topic"}
            return "✅ Creating a Zoom meeting! What’s the topic?"
        elif "google" in msg:
            user_sessions[user_id] = {"platform": "google", "step": "topic"}
            return "✅ Creating a Google Meet! What’s the topic?"
        elif "teams" in msg:
            # Check if user already authenticated
            if user_id not in teams_sessions:
                login_url = f"https://your-app.onrender.com/ms/login?user_id={user_id}"
                return f"✅ Creating a Microsoft Teams meeting!\nPlease login first: {login_url}"
            else:
                user_sessions[user_id] = {"platform": "teams", "step": "topic"}
                return "✅ Creating a Microsoft Teams meeting! What’s the topic?"
        else:
            return "❌ Say 'create zoom meeting', 'create google meeting', or 'create teams meeting'."

    session = user_sessions[user_id]

    # Topic step
    if session["step"] == "topic" and "topic" not in session:
        session["topic"] = message
        session["step"] = "time"
        return "⏰ When should the meeting start? (e.g., 'tomorrow 3pm')"

    # Time step
    elif session["step"] == "time":
        date = dateparser.parse(message)
        if not date:
            return "❌ Couldn’t understand the time. Try again (e.g., 'today 5pm')."
        session["time"] = date.strftime("%Y-%m-%dT%H:%M:%SZ")
        session["step"] = "duration"
        return "⏳ How long should the meeting be? (in minutes)"

    # Duration step
    elif session["step"] == "duration":
        try:
            duration = int(message.strip())
            session["duration"] = duration
            session["step"] = "confirm"
            return (f"✅ Confirm your {session['platform'].title()} meeting:\n"
                    f"📌 Topic: {session['topic']}\n"
                    f"⏰ Time: {session['time']}\n"
                    f"⏳ Duration: {duration} minutes\n"
                    f"Type 'yes' to confirm or 'no' to cancel.")
        except:
            return "❌ Please provide duration in numbers (e.g., 30)."

    # Confirmation step
    elif session["step"] == "confirm":
        if message.lower() == "yes":
            platform, topic, time, duration = (
                session["platform"],
                session["topic"],
                session["time"],
                session["duration"],
            )

            try:
                if platform == "zoom":
                    link = create_zoom_meeting(topic, time, duration)
                elif platform == "google":
                    link = create_google_meet(topic, time, duration)
                else:
                    if user_id not in teams_sessions:
                        login_url = f"https://whatsappbot-f8mu.onrender.com/ms/login?user_id={user_id}"
                        del user_sessions[user_id]
                        return f"❌ You need to login first: {login_url}"
                    link = create_teams_meeting(user_id, topic, time, duration)

                del user_sessions[user_id]
                return f"🎉 {platform.title()} meeting created!\n🔗 {link}"

            except Exception as e:
                return f"❌ Error creating {platform.title()} meeting: {str(e)}"
        else:
            del user_sessions[user_id]
            return "❌ Meeting creation cancelled."

# ------------------- FASTAPI ROUTE FOR WHATSAPP -------------------
@app.post("/webhook", response_class=PlainTextResponse)
async def whatsapp_webhook(request: Request):
    form = await request.form()
    incoming_msg = form.get("Body", "").strip()
    from_number = form.get("From", "").replace("whatsapp:", "")
    resp = MessagingResponse()
    try:
        reply = handle_meeting_flow(from_number, incoming_msg)
        resp.message(reply)
    except Exception as e:
        resp.message(f"❌ Error: {str(e)}")
    return Response(content=str(resp), media_type="application/xml")

# ------------------- START SERVER -------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)











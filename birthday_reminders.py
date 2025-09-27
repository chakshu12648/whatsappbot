from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from twilio.rest import Client
import pytz
from pymongo import MongoClient
import os

# MongoDB connection
MONGO_URL = os.getenv("MONGO_URL")
mongo_client = MongoClient(MONGO_URL)
db = mongo_client.whatsappbot

# Default recipient (HR/admin)
DEFAULT_RECIPIENT_PHONE = os.getenv("DEFAULT_RECIPIENT_PHONE") # e.g., whatsapp:+918290704743
TWILIO_PHONE = os.getenv("TWILIO_PHONE", "whatsapp:+14155238886")

# Sandbox join code (replace with yours)
SANDBOX_JOIN_CODE = "join somebody-cost"


def start_birthday_scheduler(twilio_client, TWILIO_PHONE, DEFAULT_RECIPIENT_PHONE):
    def send_birthday_reminders(for_tomorrow=False):
        try:
            tz = pytz.timezone("Asia/Kolkata")
            target_date = datetime.now(tz)
            if for_tomorrow:
                target_date = target_date + timedelta(days=1)

            target_ddmm = target_date.strftime("%d-%m")

            # Fetch all birthdays
            all_birthdays = list(db.birthdays.find())

            # Filter birthdays matching dd-mm
            birthdays = []
            for b in all_birthdays:
                try:
                    dob = datetime.strptime(b["date"], "%d-%m-%Y")
                    if dob.strftime("%d-%m") == target_ddmm:
                        birthdays.append(b)
                except Exception as e:
                    print(f"⚠️ Skipped invalid date for {b}: {e}")

            if not birthdays:
                print("📭 No birthdays found for reminder.")
                return

            # Prepare message
            if for_tomorrow:
                message = "⏰ Tomorrow's Birthdays:\n"
            else:
                message = "🎉 Today's Birthdays:\n"

            for b in birthdays:
                message += f"- {b['name']} ({b.get('designation', 'No designation')})\n"

            twilio_client.messages.create(
                body=message,
                from_=TWILIO_PHONE,  # Use Twilio Sandbox or your number
                to=DEFAULT_RECIPIENT_PHONE
            )
            print(f"✅ Birthday reminder sent for {len(birthdays)} employees.")

        except Exception as e:
            print(f"❌ Failed to send birthday reminders: {e}")


    # 🔹 Auto-refresh sandbox session
    def refresh_sandbox_session():
        try:
            twilio_client.messages.create(
                body=SANDBOX_JOIN_CODE,
                from_=DEFAULT_RECIPIENT_PHONE,  # your WhatsApp
                to=TWILIO_PHONE                 # Twilio Sandbox number
            )
            print("✅ Sandbox session refreshed automatically.")
        except Exception as e:
            print(f"❌ Failed to refresh sandbox session: {e}")


    # Scheduler
    scheduler = BackgroundScheduler(timezone=pytz.timezone("Asia/Kolkata"))

    # Daily at 9:00 AM → Today's birthdays
    scheduler.add_job(send_birthday_reminders, "cron", hour=9, minute=0, kwargs={"for_tomorrow": False})
    
    # Daily at 10:35 AM → Today's birthdays
    scheduler.add_job(send_birthday_reminders, "cron", hour=10, minute=35, kwargs={"for_tomorrow": False})

    # Night before at 9:00 PM → Tomorrow's birthdays
    scheduler.add_job(send_birthday_reminders, "cron", hour=21, minute=0, kwargs={"for_tomorrow": True})

    # Refresh sandbox session every 23 hours
    scheduler.add_job(refresh_sandbox_session, "interval", hours=23)

    # Run immediately on startup for testing
    send_birthday_reminders(for_tomorrow=False)
    refresh_sandbox_session()

    scheduler.start()
    print("🎂 Birthday reminder scheduler started!")





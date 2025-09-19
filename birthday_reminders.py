from datetime import datetime
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


def start_birthday_scheduler(twilio_client, TWILIO_PHONE, DEFAULT_RECIPIENT_PHONE):
    def send_birthday_reminders():
        try:
            today = datetime.now(pytz.timezone("Asia/Kolkata")).strftime("%d-%m")

            # Fetch all birthdays
            all_birthdays = list(db.birthdays.find())

            # Filter birthdays matching today's dd-mm
            today_birthdays = []
            for b in all_birthdays:
                try:
                    dob = datetime.strptime(b["date"], "%d-%m-%Y")
                    if dob.strftime("%d-%m") == today:
                        today_birthdays.append(b)
                except Exception as e:
                    print(f"⚠️ Skipped invalid date for {b}: {e}")

            if not today_birthdays:
                print("📭 No birthdays today.")
                return

            # Prepare message
            message = "🎉 Today's Birthdays:\n"
            for b in today_birthdays:
                message += f"- {b['name']} ({b.get('designation', 'No designation')})\n"

            twilio_client.messages.create(
                body=message,
                from_=TWILIO_PHONE,  # Use Twilio Sandbox or your number
                to=DEFAULT_RECIPIENT_PHONE
            )
            print(f"✅ Birthday reminder sent for {len(today_birthdays)} employees.")

        except Exception as e:
            print(f"❌ Failed to send birthday reminders: {e}")

    # Scheduler
    scheduler = BackgroundScheduler(timezone=pytz.timezone("Asia/Kolkata"))

    # Daily at 9:00 AM
    scheduler.add_job(send_birthday_reminders, "cron", hour=9, minute=0)

    
    

    # Run immediately on startup for testing
    send_birthday_reminders()

    scheduler.start()
    print("🎂 Birthday reminder scheduler started!")




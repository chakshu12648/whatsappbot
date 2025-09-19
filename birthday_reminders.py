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



def start_birthday_scheduler(twilio_client,TWILIO_PHONE,DEFAULT_RECIPIENT_PHONE):
    def send_birthday_reminders():
        try:
            today = datetime.now(pytz.timezone("Asia/Kolkata")).strftime("%d-%m")

            # Fetch birthdays from MongoDB
            today_birthdays = list(db.birthdays.find({"date": today}))

            if not today_birthdays:
                print("📭 No birthdays today.")
                return

            # Prepare message
            message = "🎉 Today's Birthdays:\n"
            for b in today_birthdays:
                message += f"- {b['name']} ({b.get('designation', 'No designation')})\n"

            # Send to default recipient
            twilio_client.messages.create(
                body=message,
                from_="whatsapp:+14155238886",  # Twilio Sandbox
                to=DEFAULT_RECIPIENT_PHONE
            )
            print(f"✅ Birthday reminder sent for {len(today_birthdays)} employees.")

        except Exception as e:
            print(f"❌ Failed to send birthday reminders: {e}")

    # Scheduler
    scheduler = BackgroundScheduler(timezone=pytz.timezone("Asia/Kolkata"))

    # Daily at 9:00 AM
    scheduler.add_job(send_birthday_reminders, "cron", hour=9, minute=0)

    # For testing: every 1 minute
    scheduler.add_job(send_birthday_reminders, "interval", minutes=1)

    # Run immediately on startup for testing
    send_birthday_reminders()

    scheduler.start()
    print("🎂 Birthday reminder scheduler started!")



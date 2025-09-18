from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from twilio.rest import Client
import pytz
import pandas as pd
import os

# Set your default recipient (HR/admin) WhatsApp numberr
DEFAULT_RECIPIENT_PHONE = os.getenv("DEFAULT_RECIPIENT_PHONE")  # e.g., "whatsapp:+911234567890"

# Path to your Excel file
EXCEL_FILE_PATH = os.getenv("BIRTHDAY_EXCEL_PATH", "employees_birthdays.xlsx")  # set path in Render env

def start_birthday_scheduler(twilio_client):
    def send_birthday_reminders():
        try:
            today = datetime.now(pytz.timezone("Asia/Kolkata")).strftime("%d-%m")
            df = pd.read_excel(EXCEL_FILE_PATH)
            df["DOB"] = pd.to_datetime(df["DOB"], errors="coerce")  # Convert to datetime
            df["dd-mm"] = df["DOB"].dt.strftime("%d-%m")

            today_birthdays = df[df["dd-mm"] == today]

            if today_birthdays.empty:
                print("📭 No birthdays today.")
                return

            # Prepare message
            message = "🎉 Today's Birthdays:\n"
            for _, row in today_birthdays.iterrows():
                message += f"- {row['Name']} ({row['Designation']})\n"

            # Send to default recipient
            twilio_client.messages.create(
                body=message,
                from_=f"whatsapp:{os.getenv('TWILIO_PHONE')}",
                to=f"whatsapp:{DEFAULT_RECIPIENT_PHONE}"
            )
            print(f"✅ Birthday reminder sent for {len(today_birthdays)} employees.")

        except Exception as e:
            print(f"❌ Failed to send birthday reminders: {e}")

    # Scheduler
    scheduler = BackgroundScheduler(timezone=pytz.timezone("Asia/Kolkata"))
    scheduler.add_job(send_birthday_reminders, "cron", hour=9, minute=0)

    # Send reminders immediately on startup
    send_birthday_reminders()

    scheduler.start()
    print("🎂 Birthday reminder scheduler started!")


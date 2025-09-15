from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from twilio.rest import Client
import pytz

def start_birthday_scheduler(db, twilio_client, twilio_phone):
    def send_birthday_reminders():
        today = datetime.now(pytz.timezone("Asia/Kolkata")).strftime("%d-%m")
        birthdays = db.birthdays.find()

        for b in birthdays:
            try:
                # Match only day-month (ignore year)
                bday_ddmm = "-".join(b["date"].split("-")[:2])
                if bday_ddmm == today:
                    twilio_client.messages.create(
                        body=f"🎉 Happy Birthday {b['name']}! 🥳 Wishing you a fantastic year ahead!",
                        from_=f"whatsapp:{twilio_phone}",
                        to=f"whatsapp:{b['phone']}"
                    )
                    print(f"✅ Birthday reminder sent to {b['name']} ({b['phone']})")
            except Exception as e:
                print(f"❌ Failed to send reminder: {e}")

    # Scheduler
    scheduler = BackgroundScheduler()
    scheduler.add_job(send_birthday_reminders, "cron", hour=9, minute=0)
    scheduler.start()

    print("🎂 Birthday reminder scheduler started!")

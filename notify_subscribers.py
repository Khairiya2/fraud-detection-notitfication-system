"""
notify_subscribers.py

Emails everyone in branch_subscriptions about any new fraud alert
raised for an agent in their branch, and only once per alert per
subscriber (tracked via subscription_notifications).

Credentials are read from environment variables — never hardcode them:
    GMAIL_ADDRESS
    GMAIL_APP_PASSWORD
    DATABASE_URL   (falls back to local DB_CONFIG if not set, same
                    pattern as fastapi_dashboard/app.py)

Run manually:
    python notify_subscribers.py

Or schedule it (e.g. Render Cron Job, or a local Task Scheduler /
cron entry) to run every few minutes so subscribers get notified
promptly after fraud_detection.py writes new alerts.
"""

import os
import psycopg2
import psycopg2.extras
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")

DATABASE_URL = os.environ.get("DATABASE_URL")
DB_CONFIG = {
    "host":     "localhost",
    "port":     "5432",
    "dbname":   "postgres",
    "user":     "postgres",
    "password": os.environ.get("LOCAL_DB_PASSWORD", ""),
}

# Only notify subscribers about alerts at/above this risk score.
# Adjust to taste — lower = more emails, higher = only serious flags.
MIN_RISK_SCORE = int(os.environ.get("SUBSCRIBER_ALERT_THRESHOLD", "21"))

DASHBOARD_URL = os.environ.get(
    "DASHBOARD_URL", "https://fraud-detection-notitfication-system-1.onrender.com"
)


def get_db():
    if DATABASE_URL:
        return psycopg2.connect(DATABASE_URL)
    return psycopg2.connect(**DB_CONFIG)


def get_unnotified_alerts():
    """Every (subscriber, alert) pair that hasn't been emailed yet,
    for alerts at/above the risk threshold."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        SELECT
            bs.subscription_id,
            bs.email          AS subscriber_email,
            bs.name           AS subscriber_name,
            b.branch_name,
            al.alert_id,
            al.agent_id,
            a.agent_name,
            al.flag_type,
            al.risk_score,
            al.triggered_at
        FROM alerts al
        JOIN agents a   ON al.agent_id  = a.agent_id
        JOIN branches b ON a.branch_id  = b.branch_id
        JOIN branch_subscriptions bs ON bs.branch_id = b.branch_id
        LEFT JOIN subscription_notifications sn
            ON sn.subscription_id = bs.subscription_id
           AND sn.alert_id        = al.alert_id
        WHERE al.risk_score >= %s
          AND sn.subscription_id IS NULL
        ORDER BY al.alert_id ASC
        """,
        (MIN_RISK_SCORE,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return rows


def mark_notified(subscription_id, alert_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO subscription_notifications (subscription_id, alert_id)
        VALUES (%s, %s)
        ON CONFLICT (subscription_id, alert_id) DO NOTHING
        """,
        (subscription_id, alert_id),
    )
    conn.commit()
    cur.close()
    conn.close()


def build_email(row):
    subject = f"[FRAUD ALERT] {row['branch_name']} — Agent {row['agent_id']} Flagged"
    greeting = f"Dear {row['subscriber_name']}," if row["subscriber_name"] else "Hello,"
    body = f"""{greeting}

This is an automated alert from the Fraud Detection System.
An agent in your branch ({row['branch_name']}) has been flagged for suspicious activity.

AGENT DETAILS

Agent ID:     {row['agent_id']}
Agent Name:   {row['agent_name']}
Branch:       {row['branch_name']}
Risk Score:   {row['risk_score']}
Flags:        {row['flag_type']}
Detected At:  {row['triggered_at']}

Login to the monitoring dashboard for full details:
{DASHBOARD_URL}

You are receiving this because you subscribed to alerts for this branch
on the Fraud Detection Dashboard.

Intelligent Fraud Detection & Customer Notification System
Micro-Insurance Company Ghana
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
    return subject, body


def send_email(to_email, subject, body):
    msg = MIMEMultipart()
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))
    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, to_email, msg.as_string())


def main():
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        print("ERROR: GMAIL_ADDRESS and GMAIL_APP_PASSWORD environment "
              "variables must be set before running this script.")
        return

    print("=" * 60)
    print("BRANCH SUBSCRIBER ALERT NOTIFIER")
    print(f"Run time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Risk score threshold: {MIN_RISK_SCORE}")
    print("=" * 60)

    pending = get_unnotified_alerts()
    print(f"\nPending subscriber notifications: {len(pending)}")

    if not pending:
        print("Nothing to send.")
        return

    sent = 0
    failed = 0

    for row in pending:
        try:
            subject, body = build_email(row)
            send_email(row["subscriber_email"], subject, body)
            mark_notified(row["subscription_id"], row["alert_id"])
            print(f"  Sent to {row['subscriber_email']} — "
                  f"Agent {row['agent_id']} (alert #{row['alert_id']})")
            sent += 1
        except Exception as e:
            print(f"  Failed for {row['subscriber_email']} "
                  f"(alert #{row['alert_id']}): {e}")
            failed += 1

    print()
    print(f"Sent:   {sent}")
    print(f"Failed: {failed}")
    print("=" * 60)


if __name__ == "__main__":
    main()

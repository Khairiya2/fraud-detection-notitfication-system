import psycopg2
import psycopg2.extras
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

# Gmail credentials
GMAIL_ADDRESS      = "khairiyaiddirs18@gmail.com"
GMAIL_APP_PASSWORD = "tsov sqbw ipua xunz"
DEMO_RECIPIENT     = "khairiyaiddirs18@gmail.com"

# Database connection
DB = {
    "host":     "localhost",
    "port":     "5432",
    "dbname":   "postgres",
    "user":     "postgres",
    "password": "riya7111#",
}

def get_db():
    return psycopg2.connect(**DB)

def get_pending_alerts():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT
            al.alert_id,
            al.agent_id,
            al.flag_type,
            al.risk_score,
            al.triggered_at,
            a.agent_name,
            a.supervisor_name,
            a.supervisor_email,
            b.branch_name,
            b.manager_name,
            b.manager_email,
            COUNT(all_alerts.alert_id) AS total_flags
        FROM alerts al
        JOIN agents a   ON al.agent_id  = a.agent_id
        JOIN branches b ON a.branch_id  = b.branch_id
        LEFT JOIN alerts all_alerts ON all_alerts.agent_id = al.agent_id
        WHERE al.status = 'sent'
        AND al.risk_score >= 51
        GROUP BY
            al.alert_id, al.agent_id, al.flag_type,
            al.risk_score, al.triggered_at,
            a.agent_name, a.supervisor_name, a.supervisor_email,
            b.branch_name, b.manager_name, b.manager_email
        ORDER BY al.risk_score DESC
    """)
    alerts = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return alerts

def update_alert_status(alert_id, status):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "UPDATE alerts SET status = %s WHERE alert_id = %s",
        (status, alert_id)
    )
    conn.commit()
    cur.close()
    conn.close()

def build_supervisor_email(alert):
    subject = (
        f"[TO: {alert['supervisor_email']}] "
        f"[FRAUD ALERT] Agent {alert['agent_id']} Flagged "
        f"{alert['branch_name']}"
        )
    body = f"""
INTENDED RECIPIENT: {alert['supervisor_email']}
(Demo mode — sent to admin inbox)

Dear {alert['supervisor_name']},
...

This is an automated alert from the Fraud Detection System.
One of your agents has been flagged for suspicious activity.

AGENT DETAILS

Agent ID:     {alert['agent_id']}
Agent Name:   {alert['agent_name']}
Branch:       {alert['branch_name']}
Risk Score:   {alert['risk_score']}
Flags:        {alert['flag_type']}
Detected At:  {alert['triggered_at']}

ACTION REQUIRED

Please investigate this agent's recent collection and remittance activity as soon as possible.

Login to the monitoring dashboard for full details:
http://192.168.1.249:7000

If this agent continues to be flagged, the case will be automatically escalated to the Branch Manager.


Intelligent Fraud Detection & Customer Notification System
Micro-Insurance Company Ghana
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    """
    return subject, body

def build_manager_email(alert):
    subject = f"[ESCALATION] Repeat Fraud Flags Agent {alert['agent_id']} , {alert['branch_name']}"
    body = f"""
    INTENDED RECIPIENT: {alert['manager_email']}
    (Demo mode — sent to admin inbox)

    Dear {alert['manager_name']},
    ...

This is an escalation alert from the Fraud Detection System.
An agent in your branch has been flagged MULTIPLE TIMES ({alert['total_flags']} times) for suspicious activity.

AGENT DETAILS

Agent ID:     {alert['agent_id']}
Agent Name:   {alert['agent_name']}
Branch:       {alert['branch_name']}
Risk Score:   {alert['risk_score']}
Flags:        {alert['flag_type']}
Total Flags:  {alert['total_flags']} times
Detected At:  {alert['triggered_at']}
Supervisor:   {alert['supervisor_name']}

URGENT ACTION REQUIRED

This agent has been flagged repeatedly. Please escalate to a formal investigation immediately.

Login to the monitoring dashboard for full details:
http://192.168.1.249:7000


Intelligent Fraud Detection & Customer Notification System
Micro-Insurance Company Ghana
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    """
    return subject, body

def send_email(to_email, subject, body):
    msg = MIMEMultipart()
    msg["From"]    = GMAIL_ADDRESS
    msg["To"]      = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))
    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, to_email, msg.as_string())

def main():
    print("=" * 60)
    print("FRAUD ALERT EMAIL SYSTEM  WITH ESCALATION")
    print(f"Run time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    alerts = get_pending_alerts()
    print(f"\nPending high risk alerts: {len(alerts)}")

    if not alerts:
        print("No new alerts to send.")
        return

    sent_to_supervisor   = 0
    escalated_to_manager = 0
    failed               = 0

    for alert in alerts:
        try:
            total_flags = int(alert["total_flags"])

            if total_flags == 1:
                subject, body = build_supervisor_email(alert)
                send_email(DEMO_RECIPIENT, subject, body)
                update_alert_status(alert["alert_id"], "acknowledged")
                print(
                    f"  SUPERVISOR notified  "
                    f"{alert['agent_id']} ({alert['agent_name']}) "
                    f"Score: {alert['risk_score']} "
                    f"Flags: {total_flags}x"
                )
                sent_to_supervisor += 1
            else:
                subject, body = build_manager_email(alert)
                send_email(DEMO_RECIPIENT, subject, body)
                update_alert_status(alert["alert_id"], "escalated")
                print(
                    f"  ESCALATED to manager  "
                    f"{alert['agent_id']} ({alert['agent_name']}) "
                    f"Score: {alert['risk_score']} "
                    f"Flags: {total_flags}x"
                )
                escalated_to_manager += 1

        except Exception as e:
            print(f"  Failed for {alert['agent_id']}: {e}")
            failed += 1

    print()
    print(f"Sent to supervisors:   {sent_to_supervisor}")
    print(f"Escalated to managers: {escalated_to_manager}")
    print(f"Failed:                {failed}")
    print("=" * 60)

if __name__ == "__main__":
    main()
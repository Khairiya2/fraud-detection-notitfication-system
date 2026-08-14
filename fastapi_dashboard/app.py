from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
import psycopg2
import psycopg2.extras
from jinja2 import Environment, FileSystemLoader
import os
import asyncio
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

app = FastAPI()

# On Render, set the DATABASE_URL environment variable (from your Postgres
# instance's "Connect" tab -> Internal or External Database URL) in the
# service's Environment tab. Locally, it falls back to your local config.
DATABASE_URL = os.environ.get("DATABASE_URL")

DB_CONFIG = {
    "host":     "localhost",
    "port":     "5432",
    "dbname":   "postgres",
    "user":     "postgres",
    "password": "riya7111#",
}

# Load Jinja2 directly, no FastAPI templating needed
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
env = Environment(loader=FileSystemLoader(os.path.join(BASE_DIR, "templates")))

# ===== Background subscriber email notifications =====
# Set these as environment variables on Render (Environment tab).
# Never hardcode real credentials here.
GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")

# How often (seconds) the background task checks for new alerts to notify
# subscribers about. Default: every 5 minutes.
NOTIFY_INTERVAL_SECONDS = int(os.environ.get("NOTIFY_INTERVAL_SECONDS", "300"))

# Only notify subscribers about alerts at/above this risk score.
SUBSCRIBER_ALERT_THRESHOLD = int(os.environ.get("SUBSCRIBER_ALERT_THRESHOLD", "21"))

DASHBOARD_URL = os.environ.get(
    "DASHBOARD_URL", "https://fraud-detection-notitfication-system-1.onrender.com"
)

def get_connection():
    if DATABASE_URL:
        # Render (and most managed Postgres providers) give a
        # postgres:// or postgresql:// URL, psycopg2 accepts it directly.
        return psycopg2.connect(DATABASE_URL)
    return psycopg2.connect(**DB_CONFIG)

def query(sql):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(sql)
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return rows

def query_one(sql):
    rows = query(sql)
    return rows[0] if rows else {}

def get_summary():
    return {
        "total_agents": query_one(
            "SELECT COUNT(*) AS c FROM agents")["c"],
        "high_risk": query_one(
            "SELECT COUNT(DISTINCT agent_id) AS c FROM alerts WHERE risk_score >= 51")["c"],
        "missed_payments": query_one("""
            SELECT COUNT(*) AS c FROM customers cu
            WHERE NOT EXISTS (
                SELECT 1 FROM collections co
                WHERE co.customer_id = cu.customers_id
                AND co.week_number = (SELECT MAX(week_number) FROM collections)
            )""")["c"],
        "total_gap": query_one("""
            SELECT ROUND((SUM(c.amount_ghs) -
                COALESCE(SUM(r.amount_ghs), 0))::NUMERIC, 2) AS gap
            FROM collections c
            LEFT JOIN remittances r ON c.collection_id = r.collection_id
            WHERE c.payment_method = 'cash'""")["gap"] or 0,
    }

def get_agent_risk():
    return query("""
        SELECT
            a.agent_id,
            a.agent_name AS name,
            b.branch_name,
            COALESCE(al.risk_score, 0) AS risk_score,
            COALESCE(al.flag_type, 'none') AS flags,
            ROUND((SUM(c.amount_ghs) -
                COALESCE(SUM(r.amount_ghs), 0))::NUMERIC, 2) AS gap_ghs,
            ROUND(AVG(CASE WHEN c.payment_method = 'cash'
                THEN 1.0 ELSE 0.0 END) * 100::NUMERIC, 1) AS cash_ratio
        FROM agents a
        JOIN branches b ON a.branch_id = b.branch_id
        LEFT JOIN collections c ON a.agent_id = c.agent_id
        LEFT JOIN remittances r ON c.collection_id = r.collection_id
        LEFT JOIN (
            SELECT DISTINCT ON (agent_id) agent_id, risk_score, flag_type
            FROM alerts ORDER BY agent_id, triggered_at DESC
        ) al ON a.agent_id = al.agent_id
        GROUP BY a.agent_id, a.agent_name, b.branch_name,
                 al.risk_score, al.flag_type
        ORDER BY risk_score DESC, gap_ghs DESC
    """)

def get_fraud_heatmap():
    return query("""
        SELECT
            a.agent_id,
            a.agent_name AS name,
            b.branch_name,
            COUNT(c.collection_id) AS total_collections,
            SUM(CASE WHEN EXTRACT(HOUR FROM c.collected_at) < 7
                      OR EXTRACT(HOUR FROM c.collected_at) >= 19
                THEN 1 ELSE 0 END) AS off_hours_count,
            COUNT(c.collection_id) - COUNT(r.remittance_id) AS ghost_count,
            ROUND((SUM(c.amount_ghs) -
                COALESCE(SUM(r.amount_ghs), 0))::NUMERIC, 2) AS gap_ghs
        FROM agents a
        JOIN branches b ON a.branch_id = b.branch_id
        LEFT JOIN collections c ON a.agent_id = c.agent_id
            AND c.payment_method = 'cash'
        LEFT JOIN remittances r ON c.collection_id = r.collection_id
        GROUP BY a.agent_id, a.agent_name, b.branch_name
        ORDER BY ghost_count DESC, off_hours_count DESC
    """)

def get_missed_payments():
    return query("""
        SELECT
            cu.customers_id,
            cu.customers_name AS name,
            cu.phone,
            cu.preferred_language AS language,
            a.agent_name AS agent,
            b.branch_name AS branch,
            (SELECT MAX(week_number) FROM collections) -
            COALESCE(MAX(co.week_number), 0) AS cycles_missed
        FROM customers cu
        JOIN agents a ON cu.agent_id = a.agent_id
        JOIN branches b ON a.branch_id = b.branch_id
        LEFT JOIN collections co ON cu.customers_id = co.customer_id
        GROUP BY cu.customers_id, cu.customers_name, cu.phone,
                 cu.preferred_language, a.agent_name, b.branch_name
        HAVING (SELECT MAX(week_number) FROM collections) -
               COALESCE(MAX(co.week_number), 0) > 0
        ORDER BY cycles_missed DESC
        LIMIT 20
    """)

def get_payment_trends():
    return query("""
        SELECT
            week_number,
            COUNT(*) AS total_payments,
            ROUND(SUM(amount_ghs)::NUMERIC, 2) AS total_amount,
            SUM(CASE WHEN payment_method = 'cash' THEN 1 ELSE 0 END) AS cash_count,
            SUM(CASE WHEN payment_method = 'momo' THEN 1 ELSE 0 END) AS momo_count
        FROM collections
        GROUP BY week_number
        ORDER BY week_number
    """)

def get_branch_performance():
    return query("""
        SELECT
            b.branch_name,
            COUNT(DISTINCT a.agent_id) AS total_agents,
            COUNT(DISTINCT c.customer_id) AS total_customers,
            ROUND(SUM(c.amount_ghs)::NUMERIC, 2) AS total_collected,
            ROUND(COALESCE(SUM(r.amount_ghs), 0)::NUMERIC, 2) AS total_remitted,
            ROUND((SUM(c.amount_ghs) -
                COALESCE(SUM(r.amount_ghs), 0))::NUMERIC, 2) AS gap_ghs,
            COUNT(DISTINCT CASE WHEN al.risk_score >= 51
                THEN a.agent_id END) AS high_risk_agents
        FROM branches b
        LEFT JOIN agents a ON b.branch_id = a.branch_id
        LEFT JOIN collections c ON a.agent_id = c.agent_id
            AND c.payment_method = 'cash'
        LEFT JOIN remittances r ON c.collection_id = r.collection_id
        LEFT JOIN alerts al ON a.agent_id = al.agent_id
        GROUP BY b.branch_name
        ORDER BY gap_ghs DESC NULLS LAST
    """)

def get_all_branches():
    """Simple branch list (id + name) for populating the subscription dropdown."""
    return query("""
        SELECT branch_id, branch_name
        FROM branches
        ORDER BY branch_name
    """)

# ===== Background subscriber email notifications =====

def get_unnotified_subscriber_alerts():
    return query(f"""
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
        WHERE al.risk_score >= {SUBSCRIBER_ALERT_THRESHOLD}
          AND sn.subscription_id IS NULL
        ORDER BY al.alert_id ASC
    """)

def mark_subscriber_notified(subscription_id, alert_id):
    conn = get_connection()
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

def build_subscriber_email(row):
    subject = f"[FRAUD ALERT] {row['branch_name']}: Agent {row['agent_id']} Flagged"
    greeting = f"Dear {row['subscriber_name']}," if row.get("subscriber_name") else "Hello,"
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

def send_subscriber_email(to_email, subject, body):
    msg = MIMEMultipart()
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))
    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, to_email, msg.as_string())

def run_subscriber_notifications():
    """Checks for any new alerts subscribers haven't been emailed about
    yet, and sends them. Safe to call repeatedly, already-notified
    alerts are skipped via subscription_notifications."""
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        print("[notify] Skipped: GMAIL_ADDRESS / GMAIL_APP_PASSWORD not set.")
        return
    try:
        pending = get_unnotified_subscriber_alerts()
    except Exception as e:
        print(f"[notify] Failed to query pending alerts: {e}")
        return
    if not pending:
        return
    print(f"[notify] Sending {len(pending)} subscriber notification(s)...")
    for row in pending:
        try:
            subject, body = build_subscriber_email(row)
            send_subscriber_email(row["subscriber_email"], subject, body)
            mark_subscriber_notified(row["subscription_id"], row["alert_id"])
            print(f"[notify] Sent to {row['subscriber_email']} "
                  f"- Agent {row['agent_id']} (alert #{row['alert_id']})")
        except Exception as e:
            print(f"[notify] Failed for {row['subscriber_email']} "
                  f"(alert #{row['alert_id']}): {e}")

async def notification_loop():
    """Runs in the background for the lifetime of the app, checking for
    new alerts to notify subscribers about every NOTIFY_INTERVAL_SECONDS."""
    while True:
        await asyncio.to_thread(run_subscriber_notifications)
        await asyncio.sleep(NOTIFY_INTERVAL_SECONDS)

@app.on_event("startup")
async def start_background_tasks():
    asyncio.create_task(notification_loop())

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, subscribed: str = None):
    try:
        template = env.get_template("index.html")
        html = template.render(
            summary       = get_summary(),
            agents        = get_agent_risk(),
            heatmap       = get_fraud_heatmap(),
            missed        = get_missed_payments(),
            trends        = get_payment_trends(),
            branches      = get_branch_performance(),
            all_branches  = get_all_branches(),
            subscribed    = subscribed,
        )
        return HTMLResponse(content=html)
    except Exception as e:
        import traceback
        return HTMLResponse(
            content=f"<pre style='color:red;padding:20px;'>{traceback.format_exc()}</pre>"
        )

@app.post("/api/subscribe")
def subscribe(branch_id: str = Form(...), email: str = Form(...), name: str = Form(None)):
    """Registers a supervisor/branch manager's email to receive alerts
    for a whole branch. Just records the signup for now, does not send
    any emails yet."""
    email_clean = email.strip().lower()
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO branch_subscriptions (branch_id, name, email)
            VALUES (%s, %s, %s)
            ON CONFLICT (branch_id, email) DO NOTHING
            """,
            (branch_id, name, email_clean),
        )
        conn.commit()
        status = "ok"
    except Exception:
        conn.rollback()
        status = "error"
    finally:
        cur.close()
        conn.close()
    return RedirectResponse(url=f"/?subscribed={status}", status_code=303)

@app.get("/api")
def api():
    return {
        "summary": get_summary(),
        "agents":  get_agent_risk(),
        "missed":  get_missed_payments(),
    }

@app.get("/api/alerts/latest")
def latest_alert_id():
    """Returns the current highest alert_id, so the frontend can remember
    where it left off (used on initial page load)."""
    row = query_one("SELECT COALESCE(MAX(alert_id), 0) AS c FROM alerts")
    return {"latest_id": row["c"]}

@app.get("/api/alerts/new")
def new_alerts(since: int = 0):
    """Returns any alerts with alert_id greater than `since`, newest first.
    The dashboard polls this endpoint to detect new fraud alerts in real time."""
    rows = query(f"""
        SELECT
            al.alert_id,
            al.agent_id,
            a.agent_name,
            al.flag_type,
            al.risk_score,
            al.triggered_at,
            al.status
        FROM alerts al
        JOIN agents a ON al.agent_id = a.agent_id
        WHERE al.alert_id > {since}
        ORDER BY al.alert_id DESC
    """)
    # Convert datetime objects to ISO strings for JSON
    for r in rows:
        if r.get("triggered_at"):
            r["triggered_at"] = r["triggered_at"].isoformat()
    return {"alerts": rows, "latest_id": rows[0]["alert_id"] if rows else since}

@app.post("/api/notify-subscribers-now")
def notify_subscribers_now():
    """Manually triggers a subscriber-notification check immediately,
    instead of waiting for the background loop's next run. Useful for
    testing right after subscribing or after a new alert is generated."""
    run_subscriber_notifications()
    return {"status": "triggered"}

if __name__ == "__main__":
    app()

import random
import psycopg2
from datetime import datetime, timedelta

random.seed(40)

db_config = {
    "host":     "localhost",
    "port":     "5432",
    "dbname":   "postgres",
    "user":     "postgres",
    "password": "riya7111#",
}

conn = psycopg2.connect(**db_config)
cur  = conn.cursor()

#Fetch agents with their collection/remittance gap
cur.execute("""
    SELECT
        a.agent_id,
        a.is_suspicious,
        ROUND((SUM(c.amount_ghs) -
            COALESCE(SUM(r.amount_ghs), 0))::NUMERIC, 2) AS gap_ghs,
        COUNT(c.collection_id) - COUNT(r.remittance_id) AS ghost_count,
        SUM(CASE
            WHEN EXTRACT(HOUR FROM c.collected_at) < 7
              OR EXTRACT(HOUR FROM c.collected_at) >= 19
            THEN 1 ELSE 0 END) AS off_hours_count
    FROM agents a
    LEFT JOIN collections c ON a.agent_id = c.agent_id
        AND c.payment_method = 'cash'
    LEFT JOIN remittances r ON c.collection_id = r.collection_id
    GROUP BY a.agent_id, a.is_suspicious
""")
agents = cur.fetchall()

print(f"Agents fetched: {len(agents)}")

FLAG_TYPES = [
    "remittance_gap",
    "ghost_collection",
    "remittance_delay",
    "high_cash_ratio",
    "off_hours_collection",
]

alerts = []
base_time = datetime.now() - timedelta(days=7)

for agent in agents:
    agent_id     = agent[0]
    is_suspicious = agent[1]
    gap_ghs      = float(agent[2] or 0)
    ghost_count  = int(agent[3] or 0)
    off_hours    = int(agent[4] or 0)

    # Calculate risk score based on actual data
    risk_score = 0
    flags = []

    if ghost_count >= 3:
        risk_score += 40
        flags.append(f"ghost_collections({ghost_count})")

    if gap_ghs > 50:
        risk_score += 25
        flags.append(f"remittance_gap(GHS{gap_ghs})")

    if off_hours > 10:
        risk_score += 15
        flags.append(f"off_hours({off_hours})")

    # Suspicious agents get extra points
    if is_suspicious:
        risk_score += 30
        flags.append("remittance_delay")

    # Only create alerts for agents with some risk
    if risk_score == 0:
        continue

    flag_type = (", ".join(flags) if flags else "suspicious_pattern")[:50]
    triggered_at = base_time + timedelta(
        days=random.randint(0, 6),
        hours=random.randint(8, 17)
    )
    status = random.choice(["sent", "sent", "sent", "acknowledged"])

    alerts.append((
        agent_id,
        flag_type,
        risk_score,
        triggered_at.strftime("%Y-%m-%d %H:%M:%S"),
        status,
    ))

# Insert alerts
cur.executemany("""
    INSERT INTO alerts
        (agent_id, flag_type, risk_score, triggered_at, status)
    VALUES (%s, %s, %s, %s, %s)
""", alerts)

conn.commit()

#Verify
cur.execute("SELECT COUNT(*) FROM alerts;")
total = cur.fetchone()[0]

cur.execute("""
    SELECT risk_score, COUNT(*) AS count
    FROM alerts
    GROUP BY risk_score
    ORDER BY risk_score DESC
""")
breakdown = cur.fetchall()

cur.execute("""
    SELECT al.agent_id, al.risk_score, al.flag_type, al.status
    FROM alerts al
    ORDER BY al.risk_score DESC
    LIMIT 10
""")
top_alerts = cur.fetchall()

print(f"Total alerts inserted: {total}")
print()
print("Risk score breakdown:")
for row in breakdown:
    print(f"  Score {row[0]:>3}  →  {row[1]} alert(s)")
print()
print("Top 10 alerts by risk score:")
for row in top_alerts:
    print(f"  {row[0]}  score={row[1]:>3}  {row[3]:>15}  {row[2]}")

cur.close()
conn.close()
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

# Fetch missed payment customers
cur.execute("""
    SELECT
        cu.customers_id,
        cu.agent_id,
        cu.preferred_language,
        (SELECT MAX(week_number) FROM collections) -
        COALESCE(MAX(co.week_number), 0) AS cycles_missed
    FROM customers cu
    LEFT JOIN collections co ON cu.customers_id = co.customers_id
    GROUP BY cu.customers_id, cu.agent_id, cu.preferred_language
    HAVING (SELECT MAX(week_number) FROM collections) -
           COALESCE(MAX(co.week_number), 0) > 0
""")
missed_customers = cur.fetchall()
print(f"Missed payment customers: {len(missed_customers)}")

RESPONSES = [
    "already_paid",
    "need_more_time",
    "speak_to_agent",
    "no_response",
]

RESPONSE_WEIGHTS = [0.2, 0.3, 0.2, 0.3]

call_logs = []
base_time = datetime.now() - timedelta(days=1)

for cust in missed_customers:
    customers_id     = cust[0]
    agent_id         = cust[1]
    preferred_language = cust[2]
    cycles_missed    = cust[3]

    response = random.choices(RESPONSES, weights=RESPONSE_WEIGHTS, k=1)[0]
    call_time = base_time + timedelta(hours=random.randint(0, 8))

    call_logs.append((
        customers_id,
        agent_id,
        call_time.strftime("%Y-%m-%d %H:%M:%S"),
        preferred_language,
        int(cycles_missed),
        response,
        f"Automated call — {cycles_missed} cycle(s) missed",
    ))

cur.executemany("""
    INSERT INTO call_logs
        (customer_id, agent_id, call_time, language_used,
         missed_cycles, customer_response, outcome_notes)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
""", call_logs)

conn.commit()

cur.execute("SELECT COUNT(*) FROM call_logs;")
total = cur.fetchone()[0]

cur.execute("""
    SELECT customer_response, COUNT(*) AS count
    FROM call_logs
    GROUP BY customer_response
    ORDER BY count DESC
""")
responses = cur.fetchall()

print(f"Call logs inserted: {total}")
print()
print("Response breakdown:")
for row in responses:
    print(f"  {row[0]:20s} → {row[1]}")

cur.close()
conn.close()

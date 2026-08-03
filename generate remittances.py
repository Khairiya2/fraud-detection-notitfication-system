import random
import psycopg2
from datetime import datetime, timedelta

random.seed(40)

#database connection
db_config = {
    "host": "localhost",
    "port": "5432",
    "dbname": "postgres",
    "user": "postgres",
    "password": "riya7111#",
}

#connect
conn = psycopg2.connect(**db_config)
cur = conn.cursor()

#fetch all CASH collections + agent suspicious status
#only remit CASH collections and momo goes straight to the company
#JOIN to agents to get the is_suspicious flag for each agent
cur.execute("""
    SELECT 
        c.collection_id,
        c.agent_id,
        c.amount_ghs,
        c.collected_at,
        c.week_number,
        a.is_suspicious
    FROM collections c
    JOIN agents a ON c.agent_id = a.agent_id
    WHERE c.payment_method = 'cash'
    ORDER BY c.collected_at
""")
cash_collections = cur.fetchall()

print(f"Cash collections fetched: {len(cash_collections)}")

#build remittance records
remittances = []
ghost_collection_ids = []
remittance_counter = 1

for col in cash_collections:
    collection_id = col[0]
    agent_id = col[1]
    amount = float(col[2])
    collected_at = col[3]
    week = col[4]
    is_suspicious = col[5]

    if not is_suspicious:
        #Honest agent
        # 98% of the time remit in full within 0-2 days
        # 2% left unremitted rare genuine human delay
        if random.random() < 0.98:
            delay_days = random.choice([0, 0, 1, 1, 2])
            remitted_at = collected_at + timedelta(
                days=delay_days,
                hours=random.randint(0, 5)
            )
            remittances.append((
                f"REM{remittance_counter:05d}",
                agent_id,
                collection_id,
                amount,
                remitted_at,
            ))
            remittance_counter += 1
        continue

    #suspicious agent
    # Behavior gets worse in the last 2 weeks
    is_late_period = week >= 7

    # Ghost collection probability
    # 15% in early weeks, rising to 30% in weeks 7 and 8
    ghost_probability = 0.30 if is_late_period else 0.15

    if random.random() < ghost_probability:
        # GHOST COLLECTION:
        #customer paid, agent recorded it, money never remitted
        #stronges fraud signal
        ghost_collection_ids.append(collection_id)
        continue  # no remittance record created at all

    #remit but late and sometimes partial
    if is_late_period:
        delay_days = random.choice([5, 6, 7, 8])
    else:
        delay_days = random.choice([3, 4, 5, 6, 7])

    remitted_at = collected_at + timedelta(
        days=delay_days,
        hours=random.randint(0, 10)
    )

    # Partial remittance: 25% of the time agent remits less than collected
    if random.random() < 0.25:
        remitted_amount = round(amount * random.choice([0.4, 0.5, 0.6, 0.7]), 2)
    else:
        remitted_amount = amount

    remittances.append((
        f"REM{remittance_counter:05d}",
        agent_id,
        collection_id,
        remitted_amount,
        remitted_at,
    ))
    remittance_counter += 1

#insert remittances into database
cur.executemany(
    """
    INSERT INTO remittances
        (remittance_id, agent_id, collection_id, amount_ghs, remitted_at)
    VALUES (%s, %s, %s, %s, %s)
    """,
    remittances,
)

#store ghost collections as hidden ground truth
# We store these in the alerts table temporarily with a special flag so we can validate our detection engine later

for ghost_id in ghost_collection_ids:
    cur.execute(
        """
        INSERT INTO alerts (agent_id, flag_type, risk_score)
        SELECT agent_id, 'GROUND_TRUTH_GHOST', 0
        FROM collections
        WHERE collection_id = %s
        """,
        (ghost_id,)
    )

conn.commit()
cur.close()

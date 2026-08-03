import psycopg2
import random
from datetime import datetime, timedelta

db_config = {
    "host": "localhost",
    "port": "5432",
    "dbname": "postgres",
    "user": "postgres",
    "password": "riya7111#"
}

#Constants
WEEKS = 8
START_DATE = datetime(2026, 5, 27)
DAY_NAME_TO_OFFSET = {
    "Monday": 0,
    "Tuesday": 1,
    "Wednesday": 2,
    "Thursday": 3,
    "Friday": 4,
}

#Connect
conn = psycopg2.connect(**db_config)
cur = conn.cursor()

#Fetch customers and their agent's suspicious status
#join customers to agents to know which agent each customer belongs to and wheeter the agent is suspicious
cur.execute("""
    SELECT c.customers_id, c.agent_id, c.expected_payment_day,
           c.policy_amount_ghs, a.is_suspicious
    FROM customers c
    JOIN agents a ON c.agent_id = a.agent_id
""")
customers = cur.fetchall()

print(f"Customers fetched from database: {len(customers)}")


#generate a realistic timestamp
def collection_timestamp(base_date, is_suspicious):
    """
    Honest agents collect between 7am and 6pm.
    Suspicious agents have a 40% chance of logging before 7am or after 7pm our off-hours fraud indicator.
    """
    if is_suspicious and random.random() < 0.40:
        #off-hours
        hour = random.choice(list(range(0, 7)) + list(range(19, 24)))
    else:
        hour = random.randint(7, 18)
    minute = random.randint(0, 59)
    return base_date.replace(hour=hour, minute=minute)


#Build collection records
collections = []
collection_counter = 1

for customer in customers:
    customer_id = customer[0]
    agent_id = customer[1]
    payment_day = customer[2]
    policy_amount = float(customer[3])
    is_suspicious = customer[4]

    day_offset = DAY_NAME_TO_OFFSET[payment_day]

    for week in range(WEEKS):
        #calculate the exact date for this payment this week
        payment_date = START_DATE + timedelta(weeks=week, days=day_offset)

        #did the customer actually pay this week?
        # 90% payment rate genuine missed payments do happen
        if random.random() > 0.90:
            continue  # genuine missed payment no collection record created

        # Payment method
        # Suspicious agents push customers toward cash (95% cash, 5% momo)
        # Honest agents follow the 85% and 15% momo
        cash_probability = 0.95 if is_suspicious else 0.85
        payment_method = "cash" if random.random() < cash_probability else "momo"

        #generate a realistic timestamp for this collection
        collected_at = collection_timestamp(payment_date, is_suspicious)

        collection_id = f"COL{collection_counter:05d}"

        collections.append((
            collection_id,
            agent_id,
            customer_id,
            policy_amount,
            payment_method,
            collected_at.strftime("%Y-%m-%d %H:%M:%S"),
            week + 1,
        ))
        collection_counter += 1

#insert into database
cur.executemany(
    """
    INSERT INTO collections
        (collection_id, agent_id, customer_id, amount_ghs,
         payment_method, collected_at, week_number)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    """,
    collections,
)

conn.commit()
cur.close()



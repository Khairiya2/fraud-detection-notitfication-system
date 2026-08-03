import random
from datetime import timedelta

import psycopg2

random.seed(42)

db_config = {
    "host" : "localhost",
    "port": "5432",
    "dbname": "postgres",
    "user": "postgres",
    "password": "riya7111#",
}

first_names = [ "Kwaku", "Yaw", "Aisha", "Rahman", "Mohammed", "Jacob",
                "Ibrahim", "Issah", "Alhassan", "Sulemana", "Abdulai",
                "Fatima", "Aisha", "Zuwera", "Mariama", "Hawa",
                "Nana", "Kojo", "Atta",  "Esi", "Yaa" , "Salama"

]

last_names = [   "Mensah", "Owusu", "Boateng", "Asante", "Osei", "Agyeman",
                 "Darko", "Appiah", "Adjei", "Acheampong", "Frimpong",
                 "Issah", "Mahama", "Abdulai", "Sulemana", "Yakubu", "Alhassan",
                 "Wiredu", "Bonsu", "Amponsah", "Nyarko", "Tetteh",

]

def names():
    return f"{random.choice(first_names)} {random.choice(last_names)}"

languages =["Twi","Dagbani"]
def pick_language():
    return random.choice(languages)


NUM_CUSTOMERS = 100
PAYMENT_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
POLICY_AMOUNTS = [10, 15, 20, 25]  # GHS per week

#connect
conn = psycopg2.connect(**db_config)
cur = conn.cursor()

#Fetch agents from database

cur.execute("""
    SELECT a.agent_id, b.region
    FROM agents a
    JOIN branches b ON a.branch_id = b.branch_id
""")
agents = cur.fetchall()

print(f"Agents fetched from database: {len(agents)}")

#build customer records
customers = []
for i in range(1, NUM_CUSTOMERS + 1):
    customers_id = f"CU{i:03d}"

    #assign this customer to one of the existing agents randomly
    agent = random.choice(agents)
    agent_id = agent[0]
    region = agent[1]

    customers_name = names()
    phone = f"0{random.choice([2,5])}{random.choice([0,4,5])}{random.randint(1000000,9999999)}"
    preferred_language = pick_language()
    expected_payment_day = random.choice(PAYMENT_DAYS)
    policy_amount_ghs = random.choice(POLICY_AMOUNTS)

    customers.append((
        customers_id,
        customers_name,
        agent_id,
        phone,
        preferred_language,
        expected_payment_day,
        policy_amount_ghs,
    ))

#insert into database
cur.executemany(
    """
    INSERT INTO customers
        (customers_id,customers_name,agent_id,phone,
         preferred_language, expected_payment_day, policy_amount_ghs)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    """,
    customers,
)

conn.commit()
cur.close()
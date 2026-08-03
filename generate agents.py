import random
import psycopg2

random.seed(42)

db_config = {
    "host" : "localhost",
    "port": "5432",
    "dbname": "postgres",
    "user": "postgres",
    "password": "riya7111#",



}

first_names = [
    "Fatima", "Daniel", "Mariam", "Issah", "Jude", "Samuel", "Farida",
    "Ibrahim", "Mavis", "Willaim", "Hawa", "Khadija","Adwoa","Aisha",
    "Kojo", "Nadia", "Khalid" ,"Esi", "Mustapha"
]

last_names =[
    "Abdullah", "Yeboah", "Alhassan", "Yakubu", "Asare", "Frimong", "Sulemana",
    "Issah", "Adjei", "Owusu", "Abdullah", "Musah", "Asante", "Mohammed",
    "Nyarko", "Rahman", "Mohammed", "Mensah", "Mohammed"
]

def names():
    return f"{random.choice(first_names)}  {random.choice(last_names)}"

branches = [
    ("BR01", "Accra", "Greater Accra", "Twi"),
    ("BR02","Tamale", "Northern Region", "Dagbani"),
    ("BR03", "Dansoman", "Greater Accra", "Twi"),
    ("BR04", "Yendi", "Northern Region", "Dagbani")
]

num_agents = 20
suspicious_agents = 5

#connect database
conn = psycopg2.connect(**db_config)
cur = conn.cursor()

#insert branches
cur.executemany(
    """INSERT INTO BRANCHES (branch_id,branch_name,region,dominant_language)
    values(%s,%s, %s, %s)
    """,
    branches
)

#agent records
agents =[]
for i in range(num_agents):
    branch_id = branches[i % len(branches)][0]
    agent_id = f"AG{i+1:03d}"
    agent_name = names()
    agent_phone = f"0{random.choice([2,5])}{random.choice([0,4,5])}{random.randint(1000000,9999999)} "
    supervisor_name = names()
    supervisor_phone = f"0{random.choice([2,5])}{random.choice([0,4,5])}{random.randint(1000000,9999999)}"
    is_suspicious = True
    agents.append([branch_id,agent_id,agent_name,agent_phone,supervisor_name,supervisor_phone, False])

#mark 5 suspicious agents randomly
suspicious_indices = random.sample(range(num_agents), suspicious_agents)
for idx in suspicious_indices:
    agents[idx][6] = True

#insert agents
cur.executemany(
    """INSERT INTO AGENTS (branch_id,agent_id,agent_name,agent_phone,supervisor_name,supervisor_phone,is_suspicious)
    values(%s,%s,%s,%s,%s,%s,%s)
    """,
    agents)



conn.commit()
cur.close()
import psycopg2

conn = psycopg2.connect(
    host="localhost",
    port="5432",
    dbname="postgres",
    user="postgres",
    password="riya7111#"
)
conn.autocommit = True
cur = conn.cursor()

cur.execute("ALTER TABLE alerts DROP CONSTRAINT alerts_status_check")
print("Constraint dropped")

cur.execute("ALTER TABLE alerts ADD CONSTRAINT alerts_status_check CHECK (status IN ('sent', 'acknowledged', 'escalated'))")
print("Constraint added")

cur.execute("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'alerts_status_check'")
print("New constraint:", cur.fetchone()[0])

cur.close()
conn.close()
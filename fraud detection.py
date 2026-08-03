import psycopg2
import pandas as pd
from sklearn.ensemble import IsolationForest
from datetime import datetime

# database connection
db_config = {
    "host":     "localhost",
    "port":     "5432",
    "dbname":   "postgres",
    "user":     "postgres",
    "password": "riya7111#",
}

conn = psycopg2.connect(**db_config)
cur  = conn.cursor()

print("=" * 60)
print("FRAUD DETECTION ENGINE")
print(f"Run time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 60)


#step 1  calculate features per agent
#feature 1 remittance gap(how much did the agent collect vs how much did they remit
cur.execute("""
    SELECT
        c.agent_id,
        ROUND(SUM(c.amount_ghs)::NUMERIC, 2)                        AS total_collected,
        ROUND(COALESCE(SUM(r.amount_ghs), 0)::NUMERIC, 2)           AS total_remitted,
        ROUND((SUM(c.amount_ghs) -
               COALESCE(SUM(r.amount_ghs), 0))::NUMERIC, 2)         AS gap_ghs
    FROM collections c
    LEFT JOIN remittances r ON c.collection_id = r.collection_id
    WHERE c.payment_method = 'cash'
    GROUP BY c.agent_id
""")
gap_data = pd.DataFrame(
    cur.fetchall(),
    columns=["agent_id", "total_collected", "total_remitted", "gap_ghs"]
)

#feature 2 average remittance delay.... (how many hours on average between collection and remittance)
cur.execute("""
    SELECT
        c.agent_id,
        ROUND(AVG(
            EXTRACT(EPOCH FROM (r.remitted_at - c.collected_at)) / 3600
        )::NUMERIC, 2) AS avg_delay_hours
    FROM collections c
    JOIN remittances r ON c.collection_id = r.collection_id
    WHERE c.payment_method = 'cash'
    GROUP BY c.agent_id
""")
delay_data = pd.DataFrame(cur.fetchall(), columns=["agent_id", "avg_delay_hours"])

#feature 3 cash ratio (what percentage of agents collection are cash vs momo)
cur.execute("""
    SELECT
        agent_id,
        ROUND(
            AVG(CASE WHEN payment_method = 'cash' THEN 1.0 ELSE 0.0 END) * 100
        ::NUMERIC, 2) AS cash_ratio
    FROM collections
    GROUP BY agent_id
""")
cash_data = pd.DataFrame(cur.fetchall(), columns=["agent_id", "cash_ratio"])

#feature 4 off hours collection (what percentage of agents collection happens outside 7am --7pm)
cur.execute("""
    SELECT
        agent_id,
        ROUND(
            AVG(CASE
                WHEN EXTRACT(HOUR FROM collected_at) < 7
                  OR EXTRACT(HOUR FROM collected_at) >= 19
                THEN 1.0 ELSE 0.0
            END) * 100
        ::NUMERIC, 2) AS off_hours_rate
    FROM collections
    GROUP BY agent_id
""")
offhours_data = pd.DataFrame(cur.fetchall(), columns=["agent_id", "off_hours_rate"])

#feature 5 ghost collection...(how many cash collection has no remittance)
cur.execute("""
    SELECT
        c.agent_id,
        COUNT(*) AS ghost_count
    FROM collections c
    LEFT JOIN remittances r ON c.collection_id = r.collection_id
    WHERE c.payment_method = 'cash'
    AND r.remittance_id IS NULL
    GROUP BY c.agent_id
""")
ghost_data = pd.DataFrame(cur.fetchall(), columns=["agent_id", "ghost_count"])

#merge all features into one table
features = gap_data.copy()
features = features.merge(delay_data,    on="agent_id", how="left")
features = features.merge(cash_data,     on="agent_id", how="left")
features = features.merge(offhours_data, on="agent_id", how="left")
features = features.merge(ghost_data,    on="agent_id", how="left")
features = features.fillna(0)

print("\n[ STEP 1 ] Features calculated per agent:")
print(features[["agent_id","gap_ghs","avg_delay_hours",
                "cash_ratio","off_hours_rate","ghost_count"]].to_string(index=False))


#step 2  rule based scoring

cur.execute("""
    SELECT a.agent_id, b.branch_name,
           ROUND(AVG(CASE WHEN c.payment_method='cash' THEN 1.0 ELSE 0.0 END)*100::NUMERIC,2) as cash_ratio
    FROM collections c
    JOIN agents a ON c.agent_id = a.agent_id
    JOIN branches b ON a.branch_id = b.branch_id
    GROUP BY a.agent_id, b.branch_name
""")
branch_cash = pd.DataFrame(cur.fetchall(), columns=["agent_id","branch_name","cash_ratio"])
branch_avg  = branch_cash.groupby("branch_name")["cash_ratio"].mean().reset_index()
branch_avg.columns = ["branch_name","branch_avg_cash"]
branch_cash = branch_cash.merge(branch_avg, on="branch_name")
features    = features.merge(branch_cash[["agent_id","branch_name","branch_avg_cash"]], on="agent_id", how="left")


def calculate_rule_score(row):
    """
    Returns (score, flag_type, details).
    flag_type: short comma-joined codes -- fits alerts.flag_type varchar(50)
    details:   full human-readable description -- goes in alerts.details (TEXT)
    """
    score = 0
    codes = []
    details = []


    #flag 1- remittance delay
    if row["avg_delay_hours"] > 48:
        score += 50
        codes.append("delay")
        details.append(f"remittance_delay({row['avg_delay_hours']}hrs)")

    #flag 2 - remittance gap-
    if row["gap_ghs"] > 50:
        score += 40
        codes.append("gap")
        details.append(f"remittance_gap(GHS{row['gap_ghs']})")

    #flag 3  high cash ratio
    if row["cash_ratio"] > row["branch_avg_cash"] + 5:
        score += 30
        codes.append("cash_ratio")
        details.append(f"high_cash_ratio({row['cash_ratio']}%)")

    #flag 4- ghost collections
    if row["ghost_count"] >= 3:
        score += 20
        codes.append("ghost")
        details.append(f"ghost_collections({int(row['ghost_count'])})")

    #flag 5- off hours
    if row["off_hours_rate"] > 20:
        score += 15
        codes.append("off_hours")
        details.append(f"off_hours({row['off_hours_rate']}%)")

    flag_type = ",".join(codes) if codes else "none"
    detail_str = ", ".join(details) if details else "none"
    return score, flag_type, detail_str


features[["rule_score","flag_type","details"]] = features.apply(
    lambda row: pd.Series(calculate_rule_score(row)), axis=1
)

print("\n[ step 2 ] Rule-based scores:")
print(features[["agent_id","rule_score","flag_type","details"]].to_string(index=False))


# step 3 isolation forest (ML anomaly detection)

ml_features = features[[
    "gap_ghs", "avg_delay_hours", "cash_ratio", "off_hours_rate", "ghost_count",
]].astype(float)

model = IsolationForest(n_estimators=100, contamination=0.25, random_state=40)
model.fit(ml_features)

features["ml_score"] = model.decision_function(ml_features)
features["ml_score"] = features["ml_score"].round(4)

print("\n[STEP 3 ] Isolation Forest anomaly scores:")
print(features[["agent_id","ml_score"]].sort_values("ml_score").to_string(index=False))


# step 4 combine scores  ie final risk

def final_risk_level(rule_score, ml_score):
    ml_anomalous = ml_score < 0
    if rule_score >= 51 and ml_anomalous:
        return "Critical"
    elif rule_score >= 51 or ml_anomalous:
        return "High"
    elif rule_score >= 21:
        return "Medium"
    else:
        return "Low"

features["risk_level"] = features.apply(
    lambda row: final_risk_level(row["rule_score"], row["ml_score"]), axis=1
)


#step 5  write alerts to database

alertable = features[features["risk_level"].isin(["Critical","High","Medium"])]

alerts_inserted = 0
for _, row in alertable.iterrows():
    cur.execute("""
        INSERT INTO alerts (agent_id, flag_type, risk_score, triggered_at, status, details)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (
        row["agent_id"],
        row["flag_type"],
        int(row["rule_score"]),
        datetime.now(),
        "sent",
        row["details"],
    ))
    alerts_inserted += 1

conn.commit()
print(f"\n[ STEP 5 ] Alerts written to database: {alerts_inserted}")


#step — final risk table(validation)

cur.execute("SELECT agent_id, agent_name, is_suspicious FROM agents")
agent_info = pd.DataFrame(cur.fetchall(), columns=["agent_id","agent_name","is_suspicious"])
final = features.merge(agent_info, on="agent_id")
final = final.sort_values("rule_score", ascending=False)

print("\n[ step ] FINAL RISK TABLE:")
print(f"\n  {'Agent':<8} {'Name':<22} {'Rule':>5} {'ML':>7} {'Risk':<10} {'Actual Suspicious'}")
print(f"  {'-'*70}")
for _, row in final.iterrows():
    print(
        f"  {row['agent_id']:<8} "
        f"{row['agent_name']:<22} "
        f"{int(row['rule_score']):>5} "
        f"{row['ml_score']:>7.4f} "
        f"{row['risk_level']:<10} "
        f"{'YES' if row['is_suspicious'] else 'no'}"
    )

print("\n[ VALIDATION ] Did the model catch the suspicious agents?")
for _, row in final[final["is_suspicious"] == True].iterrows():
    caught = row["risk_level"] in ["Critical", "High"]
    status = "CAUGHT" if caught else "MISSED"
    print(f"  {status}  {row['agent_id']}  {row['agent_name']}  →  {row['risk_level']}")

cur.close()
conn.close()
print("\n" + "=" * 60)
print("Detection engine run complete.")
print("=" * 60)
import psycopg2
import psycopg2.extras
from datetime import datetime
import time
import random


SIMULATION_MODE = True

#Africa's Talking credentials
AT_USERNAME = "sandbox"
AT_API_KEY  = "2hle4W2xT"

#Database connection
DB = {
    "host":     "localhost",
    "port":     "5432",
    "dbname":   "postgres",
    "user":     "postgres",
    "password": "riya7111#",
}

def get_db():
    return psycopg2.connect(**DB)

#Voice messages per language and missed cycle count
MESSAGES = {
    "Twi": {
        1: "Mema wo akye. Wo insurance premium a woahwehwe no atwam. Yesre wo ka no ntem.",
        2: "Wo insurance premium atwam mprenu. Yesre wo ka no ntem anaase wo policy betwa.",
        3: "Saa! Wo insurance premium atwam mprensa. Wo policy betwa wore mmere tiawa bi mu.",
    },
    "Dagbani": {
        1: "N nye di tarigi. A insurance premium be n-palli. Ti kpeng a yi kpaha di wuhigu.",
        2: "A insurance premium be n-palli yibu. Yi kpaha di wuhigu, bo n tang naa.",
        3: "A insurance premium be n-palli yeltoga. A policy nun ban kpeli.",
    },
    "English": {
        1: "Hello. Your insurance premium payment is overdue. Please make your payment as soon as possible.",
        2: "Your insurance premium is 2 cycles overdue. Please pay urgently to keep your policy active.",
        3: "Urgent. Your insurance premium is 3 or more cycles overdue. Your policy is at risk of cancellation.",
    }
}

MAX_RETRIES = 3
RETRY_DELAY = 2

SIMULATED_RESPONSES = [
    "no_response",
    "no_response",
    "already_paid",
    "need_more_time",
    "speak_to_agent",
]

def get_db():
    return psycopg2.connect(**DB)

def get_missed_customers():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT
            cu.customers_id,
            cu.customers_name AS name,
            cu.phone,
            cu.preferred_language AS language,
            a.agent_id,
            a.agent_name,
            b.branch_name,
            (SELECT MAX(week_number) FROM collections) -
            COALESCE(MAX(co.week_number), 0) AS cycles_missed
        FROM customers cu
        JOIN agents a   ON cu.agent_id  = a.agent_id
        JOIN branches b ON a.branch_id  = b.branch_id
        LEFT JOIN collections co ON cu.customers_id = co.customer_id
        GROUP BY cu.customers_id, cu.customers_name, cu.phone,
                 cu.preferred_language, a.agent_id, a.agent_name, b.branch_name
        HAVING (SELECT MAX(week_number) FROM collections) -
               COALESCE(MAX(co.week_number), 0) > 0
        ORDER BY cycles_missed DESC
    """)
    customers = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return customers

def already_called(customers_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM call_logs
        WHERE customers_id = %s
        AND call_time >= NOW() - INTERVAL '24 hours'
        AND customer_response != 'no_response'
    """, (customers_id,))
    count = cur.fetchone()[0]
    cur.close()
    conn.close()
    return count > 0

def get_message(language, cycles_missed):
    lang = language if language in MESSAGES else "English"
    cycle_key = min(cycles_missed, 3)
    return MESSAGES[lang][cycle_key]

def log_call(customers_id, agent_id, language, cycles_missed, response, notes):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO call_logs
            (customers_id, agent_id, call_time, language_used,
             missed_cycles, customer_response, outcome_notes)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (
        customers_id,
        agent_id,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        language,
        cycles_missed,
        response,
        notes,
    ))
    conn.commit()
    cur.close()
    conn.close()

def make_real_call(phone, message):
    import africastalking
    africastalking.initialize(AT_USERNAME, AT_API_KEY)
    voice = africastalking.Voice
    try:
        if phone.startswith("0"):
            phone = "+233" + phone[1:]
        response = voice.call(
            callFrom="+254711XXXYYY",
            callTo=[phone],
        )
        return True, "call_placed", response
    except Exception as e:
        return False, "no_response", str(e)

def make_simulated_call(phone, message):
    # Simulate network delay
    time.sleep(0.5)
    # 90% success rate in simulation
    if random.random() < 0.90:
        response = random.choice(SIMULATED_RESPONSES)
        return True, response, "simulated"
    else:
        return False, "no_response", "simulated_failure"

def process_customer(customer):
    customers_id  = customer["customers_id"]
    name          = customer["name"]
    phone         = customer["phone"]
    language      = customer["language"]
    agent_id      = customer["agent_id"]
    cycles_missed = int(customer["cycles_missed"])

    message = get_message(language, cycles_missed)

    print(f"\n  Customer:      {name} ({customers_id})")
    print(f"  Phone:         {phone}")
    print(f"  Language:      {language}")
    print(f"  Cycles missed: {cycles_missed}")
    print(f"  Message:       {message[:70]}...")

    for attempt in range(1, MAX_RETRIES + 1):
        print(f"  Attempt {attempt}/{MAX_RETRIES}...", end=" ")

        if SIMULATION_MODE:
            success, response, detail = make_simulated_call(phone, message)
        else:
            success, response, detail = make_real_call(phone, message)

        if success:
            print(f"SUCCESS — Customer response: {response}")
            log_call(
                customers_id, agent_id, language,
                cycles_missed, response,
                f"{'[SIMULATED] ' if SIMULATION_MODE else ''}"
                f"Call placed on attempt {attempt}. "
                f"Customer response: {response}"
            )
            return True, response

        else:
            print(f"FAILED — {detail}")
            if attempt < MAX_RETRIES:
                print(f"  Retrying in {RETRY_DELAY} seconds...")
                time.sleep(RETRY_DELAY)

    log_call(
        customers_id, agent_id, language,
        cycles_missed, "no_response",
        f"All {MAX_RETRIES} attempts failed. Agent should visit customer."
    )
    return False, "no_response"

def main():
    mode = "SIMULATION MODE" if SIMULATION_MODE else "LIVE MODE"
    print("=" * 60)
    print(f"VOICE CALL SYSTEM — {mode}")
    print(f"Run time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    if SIMULATION_MODE:
        print("\n[SIM] No real calls will be made.")
        print("[SIM] Calls and responses are simulated locally.")

    customers = get_missed_customers()
    print(f"\nCustomers with missed payments: {len(customers)}")

    if not customers:
        print("No missed payments found.")
        return

    print("\nCall Schedule:")
    print(f"  {'Customer':<12} {'Name':<22} {'Language':<10} {'Missed'}")
    print(f"  {'-'*58}")
    for c in customers:
        print(
            f"  {c['customers_id']:<12} "
            f"{c['name']:<22} "
            f"{c['language']:<10} "
            f"{c['cycles_missed']} cycle(s)"
        )

    print(f"\nStarting calls...")

    successful = 0
    failed     = 0
    skipped    = 0
    responses  = {"already_paid": 0, "need_more_time": 0,
                  "speak_to_agent": 0, "no_response": 0}

    for customer in customers:
        if already_called(customer["customers_id"]):
            print(f"\n  Skipping {customer['name']} — already called today")
            skipped += 1
            continue

        result, response = process_customer(customer)
        if result:
            successful += 1
            responses[response] = responses.get(response, 0) + 1
        else:
            failed += 1

        time.sleep(1)

    print()
    print("=" * 60)
    print(f"Calls successful: {successful}")
    print(f"Calls failed:     {failed}")
    print(f"Skipped:          {skipped}")
    print()
    print("Customer Responses:")
    for resp, count in responses.items():
        if count > 0:
            print(f"  {resp:<20} → {count}")
    print("=" * 60)

    # Show recent call logs
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT
            cl.customers_id,
            cu.customers_name AS name,
            cl.language_used,
            cl.missed_cycles,
            cl.customer_response,
            TO_CHAR(cl.call_time, 'DD Mon HH24:MI') AS call_time
        FROM call_logs cl
        JOIN customers cu ON cl.customers_id = cu.customers_id
        ORDER BY cl.call_time DESC
        LIMIT 10
    """)
    logs = cur.fetchall()
    cur.close()
    conn.close()

    if logs:
        print("\nRecent Call Logs:")
        print(f"  {'Customer':<10} {'Name':<20} {'Lang':<10} {'Response':<15} {'Time'}")
        print(f"  {'-'*68}")
        for log in logs:
            print(
                f"  {log['customers_id']:<10} "
                f"{log['name']:<20} "
                f"{log['language_used']:<10} "
                f"{log['customer_response']:<15} "
                f"{log['call_time']}"
            )

if __name__ == "__main__":
    main()
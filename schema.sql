 --BRANCHES
CREATE TABLE branches (
    branch_id    varchar(10) primary key,
    branch_name  varchar(100) not null,
    region       varchar(50) not null,
    dominant_language  varchar(20) not null
);

CREATE TABLE agents (
    agent_id varchar(10) PRIMARY KEY,
    agent_name varchar(50) not null,
    branch_id varchar(20) not null references branches(branch_id),
    agent_phone varchar(20) not null,
    supervisor_name varchar(50) not null,
    supervisor_phone varchar(20) not null,
    is_suspicious boolean default false
);



CREATE TABLE customers(
    customers_id varchar(20) primary key,
    customers_name varchar(50) not null,
    agent_id varchar(20) not null references agents(agent_id),
    preferred_language varchar(50) not null,
    expected_payment_day varchar(50) not null,
    policy_amount numeric(10, 2) not null
);




CREATE TABLE collections(
    collection_id varchar(10) primary key,
    agent_id varchar(10) not null references agents(agent_id),
    customer_id varchar(10) not null references customers(customers_id),
    amount_GHS numeric(10, 2) not null,
    payment_method varchar(10) not null check (payment_method in ('cash','momo')),
    collected_at timestamp not null,
    week_number integer not null
);

CREATE TABLE remittances(
    remittance_id varchar(10) primary key,
    agent_id varchar(10) not null references agents(agent_id),
    collection_id varchar(10) not null references collections(collection_id),
    amount_GHS numeric(10, 2) not null,
    remitted_at timestamp not null
);

CREATE TABLE ALERTS(
   alert_id serial primary key,
   agent_id varchar(10) not null references agents(agent_id),
   flag_type varchar(50) not null,
   risk_score integer not null,
   triggered_at timestamp not null default now(),
   status varchar(30) default 'sent' check (status in ('sent', 'acknoledged','excalated'))
);


CREATE TABLE call_logs(
    call_id serial primary key,
    customer_id varchar(10) not null references customers(customers_id),
    agent_id varchar(10) not null references agents(agent_id),
    call_time timestamp null default NOW(),
    language_used varchar(20) not null,
    missed_cycles integer not null,
    customer_response varchar(30)  CHECK (customer_response IN ('already_paid','need_more_time','speak_to_agent','no_response')),
    outcome_notes text
);

'Fix schema.sql'

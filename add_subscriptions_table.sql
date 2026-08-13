-- Branch alert email subscriptions
-- Lets supervisors/branch managers register an email to receive
-- fraud alert notifications for a whole branch.
CREATE TABLE IF NOT EXISTS branch_subscriptions (
    subscription_id serial primary key,
    branch_id varchar(10) not null references branches(branch_id),
    name varchar(100),
    email varchar(100) not null,
    created_at timestamp not null default now(),
    UNIQUE (branch_id, email)
);

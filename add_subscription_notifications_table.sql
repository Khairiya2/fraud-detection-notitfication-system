-- Tracks which branch_subscriptions have already been emailed about
-- which alerts, so notify_subscribers.py doesn't send duplicate emails
-- if it's run more than once.
CREATE TABLE IF NOT EXISTS subscription_notifications (
    subscription_id integer not null references branch_subscriptions(subscription_id),
    alert_id integer not null references alerts(alert_id),
    notified_at timestamp not null default now(),
    PRIMARY KEY (subscription_id, alert_id)
);

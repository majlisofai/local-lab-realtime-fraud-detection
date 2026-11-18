"""Kafka `airport.transactions` -> fraud API -> `airport.predictions` / `airport.fraud-alerts`.

Run several replicas (`make scale CONSUMERS=3`): they share the consumer group,
so Kafka splits the topic partitions between them.
"""

import json
import os
import time
from datetime import datetime, timezone

import mlflow
import requests
from confluent_kafka import Consumer, Producer
from prometheus_client import Counter, Histogram, start_http_server

from fraud import config
from fraud.monitoring.drift import DriftMonitor

PROCESSED = Counter("fraud_transactions_processed_total", "Transactions scored", ["airport", "merchant_category"])
ALERTS = Counter("fraud_alerts_total", "Fraud alerts raised", ["airport", "merchant_category"])
ERRORS = Counter("fraud_consumer_errors_total", "Processing errors", ["kind"])
E2E_LATENCY = Histogram("fraud_end_to_end_latency_seconds", "Payment event -> decision latency",
                        buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30])
PROBABILITY = Histogram("fraud_probability", "Fraud probability of scored transactions",
                        buckets=[0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0])

DRIFT_WINDOW = int(os.getenv("DRIFT_WINDOW", "200"))


def score(session: requests.Session, txn: dict) -> dict:
    """Call the serving API; wait (don't drop the event) while it is unavailable."""
    while True:
        try:
            r = session.post(f"{config.FRAUD_API_URL}/predict", json=txn, timeout=10)
            if r.status_code == 200:
                return r.json()
            ERRORS.labels(f"api_{r.status_code}").inc()
            print(f"API returned {r.status_code}: {r.text[:120]} - retrying")
        except requests.RequestException as e:
            ERRORS.labels("api_unreachable").inc()
            print(f"API unreachable ({e.__class__.__name__}) - retrying")
        time.sleep(3)


def main() -> None:
    start_http_server(8001)
    mlflow.set_tracking_uri(config.MLFLOW_TRACKING_URI)
    consumer = Consumer({
        "bootstrap.servers": config.KAFKA_BOOTSTRAP,
        "group.id": "fraud-detector",
        "auto.offset.reset": "earliest",
    })
    consumer.subscribe([config.TOPIC_TRANSACTIONS])
    producer = Producer({"bootstrap.servers": config.KAFKA_BOOTSTRAP})
    session = requests.Session()
    drift = DriftMonitor(window=DRIFT_WINDOW)
    print(f"Consuming {config.TOPIC_TRANSACTIONS}, scoring via {config.FRAUD_API_URL}")

    while True:
        msg = consumer.poll(1.0)
        if msg is None:
            continue
        if msg.error():
            ERRORS.labels("kafka").inc()
            print(f"Kafka error: {msg.error()}")
            continue

        txn = json.loads(msg.value())
        result = score(session, txn)
        decision = {**txn, **result, "decided_at": datetime.now(timezone.utc).isoformat()}

        event_time = datetime.fromisoformat(txn["event_timestamp"])
        E2E_LATENCY.observe((datetime.now(timezone.utc) - event_time).total_seconds())
        PROBABILITY.observe(result["fraud_probability"])
        labels = (txn["airport"], txn["merchant_category"])
        PROCESSED.labels(*labels).inc()

        producer.produce(config.TOPIC_PREDICTIONS, key=msg.key(), value=json.dumps(decision))
        if result["is_fraud"]:
            ALERTS.labels(*labels).inc()
            producer.produce(config.TOPIC_ALERTS, key=msg.key(), value=json.dumps(decision))
            print(f"🚨 FRAUD  {txn['airport']} {txn['merchant_category']:<17} EUR {txn['amount']:>9,.2f} "
                  f"p={result['fraud_probability']:.2f} passenger {txn['passenger_id']} (partition {msg.partition()})")
        else:
            print(f"✅ legit  {txn['airport']} {txn['merchant_category']:<17} EUR {txn['amount']:>9,.2f} "
                  f"p={result['fraud_probability']:.2f}")
        producer.poll(0)

        try:
            if not drift.rows:  # start of a window: follow the champion if it changed
                drift.set_reference(session.get(f"{config.FRAUD_API_URL}/model", timeout=5).json()["run_id"])
            drift.add(result["features"], result["is_fraud"])
        except Exception as e:
            ERRORS.labels("drift").inc()
            print(f"Drift monitoring error: {e}")


if __name__ == "__main__":
    main()

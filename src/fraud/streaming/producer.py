"""Airport payment terminals -> Kafka topic `airport.transactions`.

Switch the scenario live (no restart):  make scenario-drift | scenario-attack | scenario-normal
"""

import json
import os
import time

import numpy as np
import pandas as pd
from confluent_kafka import Producer
from prometheus_client import Counter, Gauge, start_http_server

from fraud import config
from fraud.simulation import SCENARIOS, make_passengers, make_transactions

PRODUCED = Counter("simulator_transactions_produced_total", "Transactions sent to Kafka", ["scenario"])
SCENARIO = Gauge("simulator_scenario", "Active simulator scenario (1 = active)", ["scenario"])

TPS = float(os.getenv("TRANSACTIONS_PER_SECOND", "5"))


def current_scenario() -> str:
    try:
        scenario = config.SCENARIO_FILE.read_text().strip()
    except FileNotFoundError:
        scenario = os.getenv("SCENARIO", "normal")
    return scenario if scenario in SCENARIOS else "normal"


def main() -> None:
    start_http_server(8002)
    p = config.params()["data"]
    passengers = make_passengers(p["n_passengers"], p["seed"])
    rng = np.random.default_rng()
    producer = Producer({"bootstrap.servers": config.KAFKA_BOOTSTRAP, "linger.ms": 5})
    print(f"Producing ~{TPS}/s to {config.TOPIC_TRANSACTIONS} on {config.KAFKA_BOOTSTRAP}")

    active = None
    while True:
        scenario = current_scenario()
        if scenario != active:
            print(f"--- scenario: {scenario} ---")
            for s in SCENARIOS:
                SCENARIO.labels(s).set(int(s == scenario))
            active = scenario

        txn = make_transactions(passengers, [pd.Timestamp.now(tz="UTC")], rng, scenario).iloc[0].to_dict()
        txn.pop("is_fraud")  # ground truth is not known at payment time
        txn["event_timestamp"] = txn["event_timestamp"].isoformat()
        event = {k: (v.item() if hasattr(v, "item") else v) for k, v in txn.items()}

        # Key = passenger_id: all payments of a passenger land on the same partition, in order.
        producer.produce(config.TOPIC_TRANSACTIONS, key=str(event["passenger_id"]), value=json.dumps(event))
        producer.poll(0)
        PRODUCED.labels(scenario).inc()
        print(f"sent {event['airport']} {event['merchant_category']:<17} EUR {event['amount']:>9,.2f} "
              f"passenger {event['passenger_id']}")
        time.sleep(1 / TPS)


if __name__ == "__main__":
    main()

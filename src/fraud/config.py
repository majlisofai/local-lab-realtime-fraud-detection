"""Runtime configuration: params.yaml for ML settings, environment variables for infrastructure."""

import os
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(os.getenv("LAB_ROOT", Path(__file__).resolve().parents[2]))

RAW_TRANSACTIONS = ROOT / "data/raw/transactions.parquet"
PASSENGER_PROFILES = ROOT / "data/raw/passengers.parquet"
TRAINING_EVENTS = ROOT / "data/processed/training_events.parquet"
PASSENGER_FEATURES = ROOT / "feature_repo/data/passenger_features.parquet"
FEAST_REPO = Path(os.getenv("FEAST_REPO_PATH", ROOT / "feature_repo"))
SCENARIO_FILE = ROOT / "control/scenario"
REPORTS_DIR = ROOT / "reports"

MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5001")
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9094")
FRAUD_API_URL = os.getenv("FRAUD_API_URL", "http://localhost:8000")

TOPIC_TRANSACTIONS = "airport.transactions"
TOPIC_PREDICTIONS = "airport.predictions"
TOPIC_ALERTS = "airport.fraud-alerts"


@lru_cache
def params() -> dict:
    with open(ROOT / "params.yaml") as f:
        return yaml.safe_load(f)

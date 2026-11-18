"""Step 7 - Serve: FastAPI inference service.

POST /predict  transaction -> Feast online features (Redis) -> champion model -> fraud score
POST /reload   hot-reload whatever version currently holds the @champion alias
GET  /model    which model version is serving
GET  /health   503 until a model is loaded (used by Docker healthcheck)
GET  /metrics  Prometheus metrics
"""

import threading
import time
from typing import Literal

import mlflow
import pandas as pd
from fastapi import FastAPI, HTTPException
from feast import FeatureStore
from mlflow.tracking import MlflowClient
from prometheus_client import Counter, Gauge, Histogram
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, Field

from fraud import config
from fraud.features import FEAST_FEATURES, FEATURE_SERVICE, build_model_frame
from fraud.simulation import MERCHANTS

PREDICTIONS = Counter("fraud_api_predictions_total", "Predictions served", ["outcome"])
FRAUD_PROBABILITY = Histogram("fraud_api_probability", "Predicted fraud probability",
                              buckets=[0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0])
FEAST_LATENCY = Histogram("fraud_api_feast_lookup_seconds", "Feast online lookup latency",
                          buckets=[0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25])
MODEL_LATENCY = Histogram("fraud_api_model_inference_seconds", "Model inference latency",
                          buckets=[0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25])
FEAST_MISSING = Counter("fraud_api_feast_missing_total", "Passengers without a Feast profile")
MODEL_VERSION = Gauge("fraud_model_version", "Model registry version currently serving")

Merchant = Literal[tuple(MERCHANTS)]


class Transaction(BaseModel):
    transaction_id: str | None = None
    passenger_id: int = Field(examples=[42])
    airport: str = Field("LIS", examples=["LHR"])
    merchant_category: Merchant = Field(examples=["currency_exchange"])
    amount: float = Field(gt=0, examples=[1850.0])
    hour_of_day: int = Field(ge=0, le=23, examples=[3])
    is_international: int = Field(ge=0, le=1, examples=[1])
    card_present: int = Field(ge=0, le=1, examples=[0])
    minutes_to_departure: float = Field(ge=0, examples=[25])
    event_timestamp: str | None = None


class ChampionModel:
    """Holds the model behind the registry alias; swapped atomically on reload."""

    def __init__(self) -> None:
        p = config.params()["publish"]
        self.name, self.alias = p["model_name"], p["alias"]
        self.model, self.version, self.threshold, self.run_id = None, None, 0.5, None
        self.lock = threading.Lock()

    def load(self) -> dict:
        client = MlflowClient()
        mv = client.get_model_version_by_alias(self.name, self.alias)
        model = mlflow.sklearn.load_model(f"models:/{self.name}/{mv.version}")
        threshold = float(client.get_run(mv.run_id).data.params.get("decision_threshold", 0.5))
        with self.lock:
            self.model, self.version, self.threshold, self.run_id = model, mv.version, threshold, mv.run_id
        MODEL_VERSION.set(int(mv.version))
        return self.info()

    def load_with_retry(self) -> None:
        while self.model is None:
            try:
                print(f"Loaded {self.load()}")
            except Exception as e:  # registry empty / MLflow not up yet
                print(f"Waiting for {self.name}@{self.alias}: {e}")
                time.sleep(10)

    def info(self) -> dict:
        return {"model_name": self.name, "alias": self.alias, "version": self.version,
                "run_id": self.run_id, "decision_threshold": self.threshold}


mlflow.set_tracking_uri(config.MLFLOW_TRACKING_URI)
champion = ChampionModel()
store = FeatureStore(repo_path=str(config.FEAST_REPO))

app = FastAPI(title="Airport Fraud Detection API", version="1.0")
Instrumentator().instrument(app).expose(app)
threading.Thread(target=champion.load_with_retry, daemon=True).start()


def online_features(passenger_id: int) -> dict:
    with FEAST_LATENCY.time():
        row = store.get_online_features(
            features=store.get_feature_service(FEATURE_SERVICE),
            entity_rows=[{"passenger_id": passenger_id}],
        ).to_dict()
    feats = {f: row[f][0] for f in FEAST_FEATURES}
    if all(v is None for v in feats.values()):
        FEAST_MISSING.inc()
    return feats


@app.post("/predict")
def predict(txn: Transaction) -> dict:
    if champion.model is None:
        raise HTTPException(503, "Model not loaded yet")
    started = time.perf_counter()

    feats = online_features(txn.passenger_id)
    X = build_model_frame(pd.DataFrame([{**txn.model_dump(), **feats}]))
    with champion.lock:
        model, version, threshold = champion.model, champion.version, champion.threshold
    with MODEL_LATENCY.time():
        probability = float(model.predict_proba(X)[0, 1])
    is_fraud = probability >= threshold

    PREDICTIONS.labels("fraud" if is_fraud else "legit").inc()
    FRAUD_PROBABILITY.observe(probability)
    return {
        "transaction_id": txn.transaction_id,
        "passenger_id": txn.passenger_id,
        "fraud_probability": round(probability, 4),
        "is_fraud": bool(is_fraud),
        "decision_threshold": threshold,
        "model_version": version,
        "features": X.iloc[0].to_dict(),
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
    }


@app.post("/reload")
def reload() -> dict:
    store.refresh_registry()
    try:
        return champion.load()
    except Exception as e:
        raise HTTPException(500, f"Reload failed: {e}") from e


@app.get("/model")
def model_info() -> dict:
    return champion.info()


@app.get("/health")
def health() -> dict:
    if champion.model is None:
        raise HTTPException(503, "Model not loaded yet")
    return {"status": "ok", **champion.info()}

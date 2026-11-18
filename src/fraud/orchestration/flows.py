"""Step 9 - Automate: one Prefect flow per lab stage, served as deployments.

Every stage can be started by hand from the Prefect UI (http://localhost:4200)
or the lab console (http://localhost:8090). The retrain pipeline (4 -> 5 -> 6)
also runs nightly and when Alertmanager reports data drift.

Tasks shell out to the same `uv run ...` / `docker compose ...` commands used
in the Makefile and stream their output into the Prefect logs. Each task is
tagged `component:<id>` so the lab console can light up the architecture
components a stage is working on.
"""

import os
import subprocess
import time
from datetime import datetime, timezone
from typing import Literal

import requests
from prefect import flow, get_run_logger, serve, task

from fraud import config

FEATURE_REPO = config.ROOT / "feature_repo"
# The repo is also mounted at its host path, so `docker compose` run from this
# container produces bind mounts the Docker daemon on the laptop understands.
HOST_DIR = os.getenv("LAB_HOST_DIR", str(config.ROOT))
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://prometheus:9090")


def sh(cmd: str, cwd=config.ROOT, env: dict | None = None) -> None:
    logger = get_run_logger()
    logger.info(f"$ {cmd}")
    proc = subprocess.Popen(cmd, shell=True, cwd=cwd, text=True, env={**os.environ, **(env or {})},
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    for line in proc.stdout:
        if line.strip():
            logger.info(line.rstrip())
    if proc.wait() != 0:
        raise RuntimeError(f"command failed with exit code {proc.returncode}: {cmd}")


def compose(args: str, env: dict | None = None) -> None:
    sh(f"docker compose --profile serve --profile stream {args}", cwd=HOST_DIR, env=env)


def tags(*components: str) -> list[str]:
    return [f"component:{c}" for c in components]


# ── Step 4: ingest ───────────────────────────────────────────────────────
@task(name="DVC · generate → features (parquet)", tags=tags("dvc", "parquet"))
def dvc_repro():
    sh("uv run dvc repro")


@task(name="DVC · push data version to remote", tags=tags("dvc", "parquet"))
def dvc_push():
    sh("uv run dvc push")


@task(name="Feast · apply feature definitions", tags=tags("parquet", "feast"))
def feast_apply():
    sh("uv run feast apply", cwd=FEATURE_REPO)


@task(name="Feast · materialize parquet → Redis", tags=tags("feast", "redis"))
def feast_materialize():
    end = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    sh(f"uv run feast materialize 2020-01-01T00:00:00 {end}", cwd=FEATURE_REPO)


@flow(name="step-4-ingest", description="DVC pipeline + Feast apply/materialize")
def ingest():
    dvc_repro()
    dvc_push()
    feast_apply()
    feast_materialize()


# ── Step 5: train ────────────────────────────────────────────────────────
@task(name="Train · Feast point-in-time join → 3 models → MLflow", tags=tags("feast", "trainer", "mlflow"))
def train_models():
    sh("uv run python -m fraud.training.train")


@flow(name="step-5-train", description="Train candidate models, tracked in MLflow")
def train():
    train_models()


# ── Step 6: publish ──────────────────────────────────────────────────────
@task(name="MLflow · quality gate → register → @champion", tags=tags("mlflow", "registry"))
def register_champion(force: bool):
    sh("uv run python -m fraud.training.publish --no-reload" + (" --force" if force else ""))


@task(name="API · hot-reload @champion", tags=tags("registry", "api"))
def reload_api():
    try:
        r = requests.post(f"{config.FRAUD_API_URL}/reload", timeout=60)
        get_run_logger().info(f"API serving {r.json()}")
    except requests.RequestException:
        get_run_logger().info("API not running - it loads @champion when started (step 7)")


@flow(name="step-6-publish", description="Quality gate + MLflow registry alias @champion")
def publish(force: bool = False):
    register_champion(force)
    reload_api()


# ── Step 7: serve ────────────────────────────────────────────────────────
@task(name="Docker · start scoring API", tags=tags("api"))
def start_api():
    compose("up -d --no-deps --no-build api")


@task(name="API · load @champion + connect Feast", tags=tags("registry", "redis", "api"))
def wait_for_api(timeout: int = 300):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"{config.FRAUD_API_URL}/health", timeout=5)
            if r.ok:
                get_run_logger().info(f"API healthy: {r.json()}")
                return
        except requests.RequestException:
            pass
        time.sleep(3)
    raise TimeoutError("API did not become healthy")


@task(name="API · smoke test /predict", tags=tags("redis", "api"))
def smoke_test():
    txn = {"passenger_id": 42, "airport": "DXB", "merchant_category": "currency_exchange", "amount": 2400,
           "hour_of_day": 3, "is_international": 1, "card_present": 0, "minutes_to_departure": 20}
    r = requests.post(f"{config.FRAUD_API_URL}/predict", json=txn, timeout=10)
    r.raise_for_status()
    result = r.json()
    get_run_logger().info(f"suspicious payment -> p(fraud)={result['fraud_probability']} "
                          f"is_fraud={result['is_fraud']} (model v{result['model_version']})")


@flow(name="step-7-serve", description="Start the FastAPI scoring service")
def serve_model():
    start_api()
    wait_for_api()
    smoke_test()


# ── Step 8: real-time with Kafka ─────────────────────────────────────────
@task(name="Docker · start airport payment simulator", tags=tags("producer", "kafka"))
def start_producer(transactions_per_second: float):
    compose("up -d --no-deps --no-build producer", env={"TRANSACTIONS_PER_SECOND": str(transactions_per_second)})


@task(name="Docker · start fraud consumers", tags=tags("kafka", "consumer", "api"))
def start_consumers(consumers: int):
    compose(f"up -d --no-deps --no-build --scale consumer={consumers} consumer")


@task(name="Kafka · verify payments are being scored", tags=tags("producer", "kafka", "consumer", "api"))
def verify_stream(timeout: int = 120):
    query = "sum(rate(fraud_transactions_processed_total[30s]))"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            result = requests.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": query}, timeout=5).json()
            values = result["data"]["result"]
            if values and float(values[0]["value"][1]) > 0:
                get_run_logger().info(f"Scoring {float(values[0]['value'][1]):.1f} payments/s")
                return
        except requests.RequestException:
            pass
        time.sleep(5)
    raise TimeoutError("No scored payments seen in Prometheus")


@flow(name="step-8-stream", description="Start producer + N consumers on Kafka")
def stream(consumers: int = 1, transactions_per_second: float = 5.0):
    start_producer(transactions_per_second)
    start_consumers(consumers)
    verify_stream()


@task(name="Docker · stop simulator and consumers", tags=tags("producer", "consumer"))
def stop_containers():
    compose("stop producer consumer")


@flow(name="stop-stream", description="Stop the producer and consumers")
def stop_stream():
    stop_containers()


@task(name="Simulator · switch scenario", tags=tags("producer"))
def write_scenario(scenario: str):
    config.SCENARIO_FILE.write_text(scenario + "\n")
    get_run_logger().info(f"scenario -> {scenario}")


@flow(name="scenario", description="Switch the payment simulator scenario")
def scenario(scenario: Literal["normal", "drift", "attack"] = "normal"):
    write_scenario(scenario)


# ── Retraining: nightly + on drift alert ─────────────────────────────────
@flow(name="retrain-pipeline", description="Ingest -> train -> publish (quality gate keeps a worse model out)")
def retrain(reason: str = "manual"):
    get_run_logger().info(f"retraining because: {reason}")
    ingest()
    train()
    publish()


DEPLOYMENT = "lab"


def main() -> None:
    serve(
        ingest.to_deployment(name=DEPLOYMENT, concurrency_limit=1, tags=["step-4"]),
        train.to_deployment(name=DEPLOYMENT, concurrency_limit=1, tags=["step-5"]),
        publish.to_deployment(name=DEPLOYMENT, concurrency_limit=1, tags=["step-6"]),
        serve_model.to_deployment(name=DEPLOYMENT, concurrency_limit=1, tags=["step-7"]),
        stream.to_deployment(name=DEPLOYMENT, concurrency_limit=1, tags=["step-8"]),
        stop_stream.to_deployment(name=DEPLOYMENT, concurrency_limit=1),
        scenario.to_deployment(name=DEPLOYMENT),
        retrain.to_deployment(name=DEPLOYMENT, concurrency_limit=1, cron="0 2 * * *",
                              parameters={"reason": "nightly schedule"}, tags=["step-9"]),
    )


if __name__ == "__main__":
    main()

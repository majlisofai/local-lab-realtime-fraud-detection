"""Lab console: live architecture view + one-click stage runs.

GET  /              the page (static/index.html)
GET  /api/state     component status (Prefect task runs + health + Prometheus) and stage runs
POST /api/run/{id}  start a stage = create a Prefect flow run from its deployment
POST /alertmanager  Alertmanager webhook: alerts labelled action=retrain start the retrain pipeline
"""

import asyncio
import os
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from fraud import config

PREFECT = os.getenv("PREFECT_API_URL", "http://prefect-server:4200/api")
PROMETHEUS = os.getenv("PROMETHEUS_URL", "http://prometheus:9090")
AUTO_RETRAIN = os.getenv("AUTO_RETRAIN_ON_DRIFT", "true").lower() == "true"
RETRAIN_COOLDOWN = timedelta(minutes=int(os.getenv("RETRAIN_COOLDOWN_MINUTES", "3")))

# stage id -> Prefect flow name (all deployments are called "lab")
STAGES = {
    "ingest": "step-4-ingest",
    "train": "step-5-train",
    "publish": "step-6-publish",
    "serve": "step-7-serve",
    "stream": "step-8-stream",
    "stop-stream": "stop-stream",
    "scenario": "scenario",
    "retrain": "retrain-pipeline",
}
ACTIVE = {"SCHEDULED", "PENDING", "RUNNING"}
FAILED = {"FAILED", "CRASHED"}

HEALTH_CHECKS = {
    "mlflow": f"{config.MLFLOW_TRACKING_URI}/health",
    "api": f"{config.FRAUD_API_URL}/health",
    "prometheus": f"{PROMETHEUS}/-/healthy",
    "grafana": "http://grafana:3000/api/health",
    "alertmanager": "http://alertmanager:9093/-/healthy",
    "prefect": f"{PREFECT}/health",
}

PROM_QUERIES = {
    "producer_tps": "sum(rate(simulator_transactions_produced_total[30s]))",
    "scenario": "max by (scenario) (simulator_scenario) == 1",
    "consumers": 'count(up{job="fraud-consumer"} == 1)',
    "consumer_tps": "sum(rate(fraud_transactions_processed_total[30s]))",
    "alerts_per_min": "sum(rate(fraud_alerts_total[1m])) * 60",
    "lag": 'sum(kafka_consumergroup_lag{consumergroup="fraud-detector"})',
    "kafka_brokers": "max(kafka_brokers)",
    "redis_up": "max(redis_up)",
    "redis_keys": "sum(redis_db_keys)",
    "api_p95_ms": 'histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{handler="/predict"}[1m]))) * 1000',
    "model_version": "max(fraud_model_version)",
    "drift_share": "max(evidently_data_drift_share)",
    "dataset_drift": "max(evidently_dataset_drift)",
    "firing": 'ALERTS{alertstate="firing"}',
}

app = FastAPI(title="Airport Fraud Lab Console")
client = httpx.AsyncClient(timeout=5)
events: deque = deque(maxlen=30)  # webhook / auto-retrain activity shown in the UI


def log_event(text: str) -> None:
    events.appendleft({"time": datetime.now(timezone.utc).isoformat(), "text": text})


def parse_time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


# ── Prefect ──────────────────────────────────────────────────────────────
async def prefect(path: str, body: dict | None = None) -> list | dict:
    r = await client.post(f"{PREFECT}{path}", json=body or {})
    r.raise_for_status()
    return r.json()


async def recent_flow_runs() -> list[dict]:
    soon = (datetime.now(timezone.utc) + timedelta(seconds=10)).isoformat()
    active, finished, flows = await asyncio.gather(
        prefect("/flow_runs/filter", {"flow_runs": {"state": {"type": {"any_": sorted(ACTIVE)}},
                                                    "expected_start_time": {"before_": soon}}, "limit": 20}),
        prefect("/flow_runs/filter", {"sort": "START_TIME_DESC", "limit": 30}),
        prefect("/flows/filter", {}),
    )
    names = {f["id"]: f["name"] for f in flows}
    # future runs created by the nightly schedule are not "recent"
    runs = {r["id"]: r for r in finished + active
            if r.get("state_type") and not (r["state_type"] == "SCHEDULED"
                                            and parse_time(r.get("expected_start_time")) > parse_time(soon))}
    for r in runs.values():
        r["flow_name"] = names.get(r["flow_id"], "?")
    return sorted(runs.values(), key=lambda r: r.get("expected_start_time") or "", reverse=True)


async def task_runs(flow_run_ids: list[str]) -> list[dict]:
    if not flow_run_ids:
        return []
    return await prefect("/task_runs/filter", {"flow_runs": {"id": {"any_": flow_run_ids}},
                                               "sort": "EXPECTED_START_TIME_ASC", "limit": 200})


async def deployment_id(stage: str) -> str:
    r = await client.get(f"{PREFECT}/deployments/name/{STAGES[stage]}/lab")
    if r.status_code == 404:
        raise HTTPException(503, "Deployments not registered yet - is prefect-flows running?")
    r.raise_for_status()
    return r.json()["id"]


async def create_run(stage: str, parameters: dict) -> dict:
    run = await prefect(f"/deployments/{await deployment_id(stage)}/create_flow_run", {"parameters": parameters})
    return {"flow_run_id": run["id"], "name": run["name"]}


# ── Live status ──────────────────────────────────────────────────────────
async def health(url: str) -> bool:
    try:
        return (await client.get(url, timeout=2)).status_code == 200
    except httpx.HTTPError:
        return False


async def prom(query: str) -> list:
    try:
        r = await client.get(f"{PROMETHEUS}/api/v1/query", params={"query": query}, timeout=3)
        return r.json()["data"]["result"]
    except (httpx.HTTPError, KeyError, ValueError):
        return []


def scalar(result: list) -> float | None:
    return float(result[0]["value"][1]) if result else None


async def champion_version() -> str | None:
    name, alias = config.params()["publish"]["model_name"], config.params()["publish"]["alias"]
    try:
        r = await client.get(f"{config.MLFLOW_TRACKING_URI}/api/2.0/mlflow/registered-models/alias",
                             params={"name": name, "alias": alias}, timeout=3)
        return r.json()["model_version"]["version"] if r.status_code == 200 else None
    except (httpx.HTTPError, KeyError, ValueError):
        return None


def live_components(up: dict, m: dict, champion: str | None) -> dict:
    """Is each component running right now, and a one-line detail for its box."""
    def fmt(v, spec="{:.1f}"):
        return spec.format(v) if v is not None else "–"

    scenario = m["scenario"][0]["metric"]["scenario"] if m["scenario"] else None
    firing = sorted({a["metric"]["alertname"] for a in m["firing"]})
    consumers = int(scalar(m["consumers"]) or 0)
    drift = scalar(m["dataset_drift"])
    parquet = config.PASSENGER_FEATURES.exists()
    return {
        "dvc": {"live": (config.ROOT / "dvc.lock").exists(), "detail": "dvc.lock committed" if (config.ROOT / "dvc.lock").exists() else "no data version yet"},
        "parquet": {"live": parquet, "detail": "offline store ready" if parquet else "not generated"},
        "feast": {"live": (config.FEAST_REPO / "data/registry.db").exists(), "detail": "feature service fraud_model_v1"},
        "redis": {"live": scalar(m["redis_up"]) == 1, "detail": f"{int(scalar(m['redis_keys']) or 0)} keys online"},
        "trainer": {"live": None, "detail": "runs as a job"},
        "mlflow": {"live": up["mlflow"], "detail": "tracking + artifacts"},
        "registry": {"live": champion is not None, "detail": f"@champion = v{champion}" if champion else "no champion yet"},
        "producer": {"live": (scalar(m["producer_tps"]) or 0) > 0,
                     "detail": f"{fmt(scalar(m['producer_tps']))} tx/s · {scenario or 'stopped'}"},
        "kafka": {"live": (scalar(m["kafka_brokers"]) or 0) > 0, "detail": f"lag {fmt(scalar(m['lag']), '{:.0f}')}"},
        "consumer": {"live": consumers > 0, "detail": f"{consumers} replica(s) · {fmt(scalar(m['consumer_tps']))} tx/s"},
        "api": {"live": up["api"], "detail": f"model v{fmt(scalar(m['model_version']), '{:.0f}')} · p95 {fmt(scalar(m['api_p95_ms']), '{:.0f}')} ms"},
        "evidently": {"live": drift is not None,
                      "detail": ("DRIFT" if drift else "no drift") + f" · {fmt((scalar(m['drift_share']) or 0) * 100, '{:.0f}')}% features"
                      if drift is not None else "waiting for 200 txns", "alarm": bool(drift)},
        "prometheus": {"live": up["prometheus"], "detail": f"{len(firing)} alert(s) firing" if firing else "no alerts"},
        "grafana": {"live": up["grafana"], "detail": "dashboards"},
        "alertmanager": {"live": up["alertmanager"], "detail": ", ".join(firing) if firing else "quiet", "alarm": bool(firing)},
        "prefect": {"live": up["prefect"], "detail": "orchestrator"},
    }


def task_components(runs: list[dict], tasks: list[dict]) -> dict:
    """Which components Prefect tasks are working on now (running) or just finished (done / failed)."""
    now = datetime.now(timezone.utc)
    rank = {"running": 3, "failed": 2, "done": 1}
    status: dict[str, str] = {}
    for t in tasks:
        state, ended = t.get("state_type"), parse_time(t.get("end_time"))
        if state == "RUNNING":
            s = "running"
        elif state in FAILED and ended and now - ended < timedelta(minutes=3):
            s = "failed"
        elif state == "COMPLETED" and ended and now - ended < timedelta(seconds=45):
            s = "done"
        else:
            continue
        for tag in t.get("tags", []):
            if tag.startswith("component:"):
                c = tag.split(":", 1)[1]
                if rank[s] > rank.get(status.get(c), 0):
                    status[c] = s
    if any(r["state_type"] == "RUNNING" for r in runs):
        status["prefect"] = "running"
    return status


@app.get("/api/state")
async def state() -> dict:
    up_values = await asyncio.gather(*(health(u) for u in HEALTH_CHECKS.values()))
    up = dict(zip(HEALTH_CHECKS, up_values))
    prom_values = await asyncio.gather(*(prom(q) for q in PROM_QUERIES.values()))
    metrics = dict(zip(PROM_QUERIES, prom_values))
    components = live_components(up, metrics, await champion_version())

    stages, recent_tasks = {}, []
    if up["prefect"]:
        try:
            runs = await recent_flow_runs()
            tasks = await task_runs([r["id"] for r in runs[:25]])
            for c, s in task_components(runs, tasks).items():
                components.setdefault(c, {})["task"] = s
            by_run: dict[str, list] = {}
            for t in tasks:
                by_run.setdefault(t["flow_run_id"], []).append(t)
            for stage, flow_name in STAGES.items():
                run = next((r for r in runs if r["flow_name"] == flow_name), None)
                if run:
                    stages[stage] = {
                        "flow_run_id": run["id"], "name": run["name"], "state": run["state_type"],
                        "state_name": run.get("state_name"), "start": run.get("start_time"),
                        "end": run.get("end_time"), "parameters": run.get("parameters", {}),
                        "tasks": [{"name": t["name"], "state": t["state_type"]} for t in by_run.get(run["id"], [])],
                    }
            recent_tasks = sorted(
                ({"name": t["name"], "state": t["state_type"], "time": t.get("end_time") or t.get("start_time")}
                 for t in tasks if t.get("start_time")),
                key=lambda t: t["time"] or "", reverse=True)[:14]
        except httpx.HTTPError as e:
            log_event(f"Prefect API error: {e}")

    return {"components": components, "stages": stages, "tasks": recent_tasks,
            "events": list(events), "auto_retrain": AUTO_RETRAIN}


@app.post("/api/run/{stage}")
async def run_stage(stage: str, parameters: dict | None = None) -> dict:
    if stage not in STAGES:
        raise HTTPException(404, f"unknown stage {stage}")
    run = await create_run(stage, parameters or {})
    log_event(f"▶ {STAGES[stage]} started from the console ({run['name']})")
    return run


@app.post("/alertmanager")
async def alertmanager(payload: dict) -> dict:
    alerts = payload.get("alerts", [])
    for a in alerts:
        log_event(f"🔔 Alertmanager: {a['labels'].get('alertname')} {a.get('status')}")
    retrain = [a for a in alerts if a.get("status") == "firing" and a["labels"].get("action") == "retrain"]
    if not retrain:
        return {"retrain": False}
    if not AUTO_RETRAIN:
        log_event("auto-retrain disabled (AUTO_RETRAIN_ON_DRIFT=false)")
        return {"retrain": False}

    runs = [r for r in await recent_flow_runs() if r["flow_name"] == STAGES["retrain"]]
    now = datetime.now(timezone.utc)
    if runs and (runs[0]["state_type"] in ACTIVE or
                 (parse_time(runs[0].get("end_time")) or now - RETRAIN_COOLDOWN) > now - RETRAIN_COOLDOWN):
        log_event("retrain already running or ran recently - skipped (cooldown)")
        return {"retrain": False}
    reason = ", ".join(sorted({a["labels"]["alertname"] for a in retrain}))
    run = await create_run("retrain", {"reason": f"alert: {reason}"})
    log_event(f"🔁 auto-retrain started by {reason} ({run['name']})")
    return {"retrain": True, **run}


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(Path(__file__).parent / "static/index.html", headers={"Cache-Control": "no-cache"})

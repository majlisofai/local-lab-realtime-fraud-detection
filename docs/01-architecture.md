# Step 1 — High-Level Architecture

Real-time fraud detection for **card payments at airports** (duty free, currency
exchange, airline tickets, lounges, car rental…). Everything runs on one laptop
as Docker containers orchestrated by Docker Compose — no Kubernetes.

```mermaid
%%{init: {"theme": "base", "themeVariables": {"fontFamily": "IBM Plex Sans, Segoe UI, sans-serif", "fontSize": "14px", "background": "#FFFFFF", "primaryColor": "#FFFFFF", "primaryTextColor": "#111111", "primaryBorderColor": "#111111", "secondaryColor": "#F5F5F5", "tertiaryColor": "#FFFFFF", "lineColor": "#5C5C5C", "textColor": "#111111", "mainBkg": "#FFFFFF", "clusterBkg": "#FFFFFF", "clusterBorder": "#D9D9D9", "edgeLabelBackground": "#FFFFFF", "noteBkgColor": "#F5F5F5", "noteTextColor": "#111111", "noteBorderColor": "#D9D9D9", "actorBkg": "#FFFFFF", "actorBorder": "#111111", "signalColor": "#111111", "pie1": "#111111", "pie2": "#5C5C5C", "pie3": "#CC3A1C"}}}%%
flowchart LR
    %% ---------- Sources ----------
    subgraph SRC["Airport payment terminals"]
        SIM["Payment simulator<br/>(producer)<br/>normal · drift · attack"]
    end

    %% ---------- Data & features ----------
    subgraph DATA["Data & Feature Store"]
        DVC["DVC pipeline<br/>generate → features<br/>(parquet)"]
        REMOTE[("DVC remote<br/>dvc-storage/")]
        OFF[("Feast offline store<br/>passenger_features.parquet")]
        ONL[("Feast online store<br/>Redis")]
    end

    %% ---------- ML platform ----------
    subgraph ML["ML Platform"]
        TRAIN["Trainer job<br/>scikit-learn"]
        MLF["MLflow<br/>tracking + registry<br/>@champion"]
        PG[("Postgres<br/>runs & registry")]
        ART[("Artifact store<br/>models · reference data")]
    end

    %% ---------- Streaming ----------
    subgraph STREAM["Streaming — Apache Kafka (KRaft)"]
        T1[["airport.transactions<br/>3 partitions"]]
        T2[["airport.predictions"]]
        T3[["airport.fraud-alerts"]]
    end

    %% ---------- Serving ----------
    subgraph SERVE["Real-time inference"]
        CONS["Fraud consumer(s)<br/>scale ×N<br/>+ Evidently drift"]
        API["FastAPI scoring service<br/>/predict · /reload"]
    end

    %% ---------- Monitoring ----------
    subgraph MON["Monitoring"]
        PROM["Prometheus<br/>+ alert rules"]
        GRAF["Grafana dashboards"]
        EXP["Exporters<br/>kafka · redis · cAdvisor"]
        EVR["Evidently HTML report"]
    end

    DVC -- dvc push --> REMOTE
    DVC --> OFF
    OFF -- feast materialize --> ONL
    OFF -- point-in-time join --> TRAIN
    TRAIN -- runs, metrics, models --> MLF
    MLF --- PG
    MLF --- ART

    SIM -- key = passenger_id --> T1
    T1 --> CONS
    CONS -- HTTP --> API
    API -- passenger features --> ONL
    API -- load @champion --> MLF
    CONS --> T2
    CONS -- is_fraud --> T3
    CONS -- reference data --> MLF

    API -. /metrics .-> PROM
    CONS -. /metrics .-> PROM
    SIM -. /metrics .-> PROM
    EXP -. /metrics .-> PROM
    PROM --> GRAF
    CONS --> EVR
```

## Components

| Layer | Container(s) | Role | Port |
|---|---|---|---|
| Streaming | `kafka`, `kafka-init`, `kafka-ui` | Event backbone (KRaft, no ZooKeeper); topics created with 3 partitions | 9094, UI 8080 |
| Feature store | `redis` + Feast (library) | Offline store = parquet (training) · online store = Redis (serving) | 6379 |
| Data versioning | DVC (in `trainer`) | Reproducible data pipeline, parquet versioned in `dvc-storage/` | — |
| Model management | `mlflow`, `postgres` | Experiment tracking, model registry, artifact serving | 5001 |
| Training jobs | `trainer` (profile `jobs`) | DVC / Feast / training / publishing, run on demand | — |
| Serving | `api` | FastAPI: Feast enrichment + champion model, hot reload | 8000 |
| Real-time | `producer`, `consumer` ×N | Simulator → Kafka → scoring → predictions/alerts topics | — |
| Monitoring | `prometheus`, `grafana`, `kafka-exporter`, `redis-exporter`, `cadvisor` | Infra + app + model metrics, dashboards, alert rules | 9090, 3000, 8081 |
| Automation (step 9) | `prefect-server`, `prefect-flows`, `alertmanager`, `lab-console` | Run each stage from a UI, nightly + drift-triggered retraining, live architecture view | 4200, 9093, 8090 |

## The airport analogy (for the class)

Think of the system as an **airport security checkpoint** for money:

| Airport | System |
|---|---|
| Passengers arriving at security, one queue per lane | Payments arriving on **Kafka** partitions (one passenger always uses the same lane = message key) |
| The traveller's file with past trips | **Feast** passenger profile: 30-day spend, trips in 7 days, airports visited |
| The archive room vs. the officer's screen | **Offline store** (parquet, full history) vs. **online store** (Redis, latest value, sub-millisecond) |
| The security manual, with versions and an approved edition | **MLflow** registry; `@champion` = the edition officers must use |
| The security officer | **FastAPI** scoring service |
| The supervisor dispatching travellers to officers | **Consumer group**: add officers (`make scale`) and Kafka redistributes the lanes |
| The control room with CCTV and counters | **Prometheus + Grafana** |
| The auditor checking whether today's travellers still look like the ones in the manual | **Evidently** data drift |

## Why no Kubernetes?

Docker Compose gives us everything needed to *learn* the architecture on a laptop:
service discovery by DNS name, health checks, dependency ordering, profiles,
and horizontal scaling (`docker compose up --scale consumer=3`). Mapping to Kubernetes later
is mechanical:

| Docker Compose | Kubernetes |
|---|---|
| service | Deployment + Service |
| `--scale consumer=3` | `replicas: 3` / HPA (KEDA on Kafka lag) |
| `healthcheck` | readiness / liveness probes |
| named volume | PersistentVolumeClaim |
| `profiles: [jobs]` + `docker compose run trainer` | Job / CronJob (or Argo / Kubeflow pipeline) |
| Prometheus `dns_sd_configs` | Prometheus Operator `ServiceMonitor` |

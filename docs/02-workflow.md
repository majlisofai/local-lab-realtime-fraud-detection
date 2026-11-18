# Step 2 — Workflow: from Data Ingestion to Model Serving and Monitoring

> Also available as an editable ArchiMate view: [diagrams/02-workflow-archimate.drawio](diagrams/02-workflow-archimate.drawio) ([PNG](diagrams/02-workflow-archimate.png)).

## End-to-end flow

```mermaid
%%{init: {"theme": "base", "themeVariables": {"fontFamily": "IBM Plex Sans, Segoe UI, sans-serif", "fontSize": "14px", "background": "#FFFFFF", "primaryColor": "#FFFFFF", "primaryTextColor": "#111111", "primaryBorderColor": "#111111", "secondaryColor": "#F5F5F5", "tertiaryColor": "#FFFFFF", "lineColor": "#5C5C5C", "textColor": "#111111", "mainBkg": "#FFFFFF", "clusterBkg": "#FFFFFF", "clusterBorder": "#D9D9D9", "edgeLabelBackground": "#FFFFFF", "noteBkgColor": "#F5F5F5", "noteTextColor": "#111111", "noteBorderColor": "#D9D9D9", "actorBkg": "#FFFFFF", "actorBorder": "#111111", "signalColor": "#111111", "pie1": "#111111", "pie2": "#5C5C5C", "pie3": "#CC3A1C"}}}%%
flowchart TB
    subgraph S4["4 · Ingest — DVC + Feast  (make ingest)"]
        direction LR
        G["dvc stage: generate<br/>60 days of airport payments<br/>→ data/raw/*.parquet"]
        F["dvc stage: features<br/>daily passenger snapshots<br/>→ passenger_features.parquet<br/>→ training_events.parquet"]
        P["dvc push<br/>→ dvc-storage/"]
        A["feast apply<br/>register entity, view, service"]
        M["feast materialize<br/>parquet → Redis"]
        G --> F --> P --> A --> M
    end

    subgraph S5["5 · Train — MLflow tracking  (make train)"]
        direction LR
        H["Feast get_historical_features<br/>point-in-time join"]
        SPL["time-based split<br/>train · valid · test"]
        C["3 candidates<br/>logistic · random forest · gradient boosting"]
        L["log params, metrics, threshold,<br/>confusion matrix, model + signature,<br/>Evidently reference, data version"]
        H --> SPL --> C --> L
    end

    subgraph S6["6 · Publish — MLflow registry  (make publish)"]
        direction LR
        B["pick best run<br/>by test PR-AUC"]
        Q{"quality gate<br/>≥ min & > champion?"}
        R["register version<br/>alias @champion<br/>old → @previous"]
        RL["POST /reload<br/>on the API"]
        B --> Q -- yes --> R --> RL
        Q -- no --> X["stop: keep current champion"]
    end

    subgraph S7["7 · Serve — FastAPI  (make serve · make predict)"]
        direction LR
        REQ["POST /predict"] --> ENR["Feast online lookup<br/>(Redis)"] --> SC["champion model<br/>predict_proba ≥ threshold"] --> RESP["fraud_probability,<br/>is_fraud, model_version"]
    end

    subgraph S8["8 · Real-time with Kafka  (make stream)"]
        direction LR
        PR["producer<br/>airport terminals"] --> K[["airport.transactions"]] --> CO["consumer group<br/>fraud-detector"]
        CO --> APIc["/predict"]
        CO --> KP[["airport.predictions"]]
        CO --> KA[["airport.fraud-alerts"]]
    end

    subgraph MON["Monitoring — Prometheus · Grafana · Evidently"]
        direction LR
        MET["/metrics<br/>api · consumer · simulator · exporters"] --> PRM["Prometheus<br/>alert rules"] --> GF["Grafana dashboard"]
        EV["Evidently every 200 txns<br/>live vs. reference"] --> MET
        EV --> HTML["reports/drift_report.html"]
    end

    S4 --> S5 --> S6 --> S7 --> S8 --> MON
    MON -. "drift / performance drop → retrain" .-> S4
```

## Real-time path of one payment

```mermaid
%%{init: {"theme": "base", "themeVariables": {"fontFamily": "IBM Plex Sans, Segoe UI, sans-serif", "fontSize": "14px", "background": "#FFFFFF", "primaryColor": "#FFFFFF", "primaryTextColor": "#111111", "primaryBorderColor": "#111111", "secondaryColor": "#F5F5F5", "tertiaryColor": "#FFFFFF", "lineColor": "#5C5C5C", "textColor": "#111111", "mainBkg": "#FFFFFF", "clusterBkg": "#FFFFFF", "clusterBorder": "#D9D9D9", "edgeLabelBackground": "#FFFFFF", "noteBkgColor": "#F5F5F5", "noteTextColor": "#111111", "noteBorderColor": "#D9D9D9", "actorBkg": "#FFFFFF", "actorBorder": "#111111", "signalColor": "#111111", "pie1": "#111111", "pie2": "#5C5C5C", "pie3": "#CC3A1C"}}}%%
sequenceDiagram
    autonumber
    participant T as Airport terminal<br/>(producer)
    participant K as Kafka<br/>airport.transactions
    participant C as Fraud consumer
    participant A as FastAPI /predict
    participant R as Redis<br/>(Feast online)
    participant M as Model @champion<br/>(in API memory)
    participant O as Kafka<br/>predictions / alerts
    participant P as Prometheus

    T->>K: payment event (key = passenger_id)
    K->>C: poll (consumer group fraud-detector)
    C->>A: POST /predict {amount, merchant, airport, ...}
    A->>R: get_online_features(passenger_id)
    R-->>A: avg_amount_30d, txn_count_7d, distinct_airports_30d, account_age_days
    A->>M: build_model_frame() → predict_proba
    M-->>A: p(fraud)
    A-->>C: {fraud_probability, is_fraud, model_version, features}
    C->>O: decision → airport.predictions
    alt is_fraud
        C->>O: alert → airport.fraud-alerts
    end
    C->>C: buffer features for Evidently (window = 200)
    P-->>A: scrape /metrics (latency, predictions)
    P-->>C: scrape /metrics (throughput, alerts, drift, e2e latency)
```

## Lifecycle of a model (what changes when)

| Event | What runs | Result |
|---|---|---|
| New data / params changed | `make ingest` | new `dvc.lock` → commit = new **data version**; Redis refreshed |
| Code or data changed | `make train` | new MLflow runs tagged with `data_version` + `git_commit` |
| Better run available | `make publish` | new registry version → `@champion`; API hot-reloads, no downtime |
| Bad release | set `@champion` back to the `@previous` version in MLflow UI, then `curl -X POST localhost:8000/reload` | rollback in seconds |
| Drift detected (Grafana / alert) | inspect `reports/drift_report.html` → retrain on fresh data | closes the MLOps loop |

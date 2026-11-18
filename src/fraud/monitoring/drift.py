"""Model monitoring with Evidently: live features vs. the champion's training reference.

Every `window` scored transactions an Evidently DataDriftPreset report is run.
Results are exported as Prometheus gauges (-> Grafana) and the full HTML
report is written to reports/drift_report.html for inspection.
"""

import mlflow
import pandas as pd
from evidently import ColumnMapping
from evidently.metric_preset import DataDriftPreset
from evidently.report import Report
from prometheus_client import Gauge

from fraud import config
from fraud.features import DRIFT_COLUMNS, TXN_CATEGORICAL

DRIFT_SHARE = Gauge("evidently_data_drift_share", "Share of monitored features that drifted")
DATASET_DRIFT = Gauge("evidently_dataset_drift", "1 if Evidently flags dataset drift")
DRIFTED_FEATURES = Gauge("evidently_drifted_features", "Number of drifted features")
FEATURE_DRIFT = Gauge("evidently_feature_drift_score", "Per-feature drift test score (p-value / distance)",
                      ["feature", "stattest"])
FEATURE_DRIFTED = Gauge("evidently_feature_drift_detected", "1 if the feature drifted", ["feature"])
WINDOW_FRAUD_RATE = Gauge("monitoring_window_fraud_rate", "Share of transactions flagged in the last window")

COLUMN_MAPPING = ColumnMapping(
    numerical_features=[c for c in DRIFT_COLUMNS if c not in TXN_CATEGORICAL + ["is_international", "card_present"]],
    categorical_features=TXN_CATEGORICAL + ["is_international", "card_present"],
)


def load_reference(run_id: str) -> pd.DataFrame:
    path = mlflow.artifacts.download_artifacts(run_id=run_id, artifact_path="reference/reference.parquet")
    return pd.read_parquet(path)[DRIFT_COLUMNS]


class DriftMonitor:
    def __init__(self, window: int) -> None:
        self.window = window
        self.reference: pd.DataFrame | None = None
        self.reference_run: str | None = None
        self.rows: list[dict] = []
        self.flags: list[bool] = []

    def set_reference(self, run_id: str) -> None:
        if run_id != self.reference_run:
            self.reference = load_reference(run_id)
            self.reference_run = run_id
            print(f"Drift reference loaded from run {run_id[:8]} ({len(self.reference)} rows)")

    def add(self, features: dict, is_fraud: bool) -> None:
        self.rows.append({c: features.get(c) for c in DRIFT_COLUMNS})
        self.flags.append(is_fraud)
        if len(self.rows) >= self.window and self.reference is not None:
            self.evaluate(pd.DataFrame(self.rows))
            self.rows, self.flags = [], []

    def evaluate(self, current: pd.DataFrame) -> None:
        report = Report(metrics=[DataDriftPreset()])
        report.run(reference_data=self.reference, current_data=current, column_mapping=COLUMN_MAPPING)

        dataset, table = (m["result"] for m in report.as_dict()["metrics"][:2])
        DRIFT_SHARE.set(dataset["share_of_drifted_columns"])
        DATASET_DRIFT.set(int(dataset["dataset_drift"]))
        DRIFTED_FEATURES.set(dataset["number_of_drifted_columns"])
        for feature, col in table["drift_by_columns"].items():
            FEATURE_DRIFT.labels(feature, col["stattest_name"]).set(col["drift_score"])
            FEATURE_DRIFTED.labels(feature).set(int(col["drift_detected"]))
        WINDOW_FRAUD_RATE.set(sum(self.flags) / len(self.flags))

        config.REPORTS_DIR.mkdir(exist_ok=True)
        report.save_html(str(config.REPORTS_DIR / "drift_report.html"))
        drifted = [f for f, c in table["drift_by_columns"].items() if c["drift_detected"]]
        print(f"📈 Evidently: {dataset['number_of_drifted_columns']}/{dataset['number_of_columns']} features "
              f"drifted (dataset drift={dataset['dataset_drift']}) {drifted}")

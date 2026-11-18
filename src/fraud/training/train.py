"""Step 5 - Train: Feast offline store (point-in-time join) -> scikit-learn -> MLflow tracking.

Trains one MLflow run per candidate model. Every run logs params, metrics,
the data version (DVC), a confusion matrix, the model with its signature and
a reference sample that Evidently later uses to detect drift.
"""

import subprocess
import tempfile
import uuid
import warnings
from pathlib import Path

import matplotlib.pyplot as plt
import mlflow
import numpy as np
import pandas as pd
import yaml
from feast import FeatureStore
from mlflow.models import infer_signature
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    ConfusionMatrixDisplay, average_precision_score, f1_score, precision_recall_curve,
    precision_score, recall_score, roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from fraud import config
from fraud.features import (
    DRIFT_COLUMNS, FEATURE_SERVICE, MODEL_FEATURES, NUMERIC_FEATURES, TXN_CATEGORICAL, build_model_frame,
)


def load_training_set() -> pd.DataFrame:
    """Labelled events + passenger features as they were known at each event time."""
    entity_df = pd.read_parquet(config.TRAINING_EVENTS)
    store = FeatureStore(repo_path=str(config.FEAST_REPO))
    df = store.get_historical_features(
        entity_df=entity_df, features=store.get_feature_service(FEATURE_SERVICE)
    ).to_df()
    return df.sort_values("event_timestamp").reset_index(drop=True)


def time_split(df: pd.DataFrame, valid_size: float, test_size: float):
    n = len(df)
    a, b = int(n * (1 - valid_size - test_size)), int(n * (1 - test_size))
    return df.iloc[:a], df.iloc[a:b], df.iloc[b:]


def build_pipeline(name: str, hp: dict, seed: int) -> Pipeline:
    if name == "logistic_regression":
        numeric, clf = StandardScaler(), LogisticRegression(max_iter=2000, class_weight="balanced", **hp)
    elif name == "random_forest":
        numeric = "passthrough"
        clf = RandomForestClassifier(class_weight="balanced_subsample", n_jobs=-1, random_state=seed, **hp)
    elif name == "hist_gradient_boosting":
        numeric, clf = "passthrough", HistGradientBoostingClassifier(class_weight="balanced", random_state=seed, **hp)
    else:
        raise ValueError(f"unknown model {name}")
    pre = ColumnTransformer([
        ("num", numeric, NUMERIC_FEATURES),
        ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), TXN_CATEGORICAL),
    ])
    return Pipeline([("features", pre), ("model", clf)])


def best_threshold(y_true, proba) -> float:
    """Decision threshold that maximises F1 on the validation set."""
    precision, recall, thresholds = precision_recall_curve(y_true, proba)
    f1 = 2 * precision * recall / np.clip(precision + recall, 1e-9, None)
    return float(thresholds[np.argmax(f1[:-1])])


def data_version() -> str:
    """md5 of the DVC `features` stage output - ties every run to an exact dataset version."""
    lock = config.ROOT / "dvc.lock"
    if not lock.exists():
        return "untracked"
    outs = yaml.safe_load(lock.read_text())["stages"]["features"]["outs"]
    return ",".join(o["md5"][:12] for o in outs)


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=config.ROOT, text=True,
                                       stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "unknown"


def main() -> None:
    p = config.params()["train"]
    seed = config.params()["data"]["seed"]
    mlflow.set_tracking_uri(config.MLFLOW_TRACKING_URI)
    mlflow.set_experiment(p["experiment"])

    df = load_training_set()
    # Feast resets the warning filters on load; silence protobuf/MLflow deprecation noise for the class
    warnings.simplefilter("ignore", DeprecationWarning)
    warnings.simplefilter("ignore", UserWarning)
    train_df, valid_df, test_df = time_split(df, p["valid_size"], p["test_size"])
    X_train, X_valid, X_test = (build_model_frame(d) for d in (train_df, valid_df, test_df))
    y_train, y_valid, y_test = (d["is_fraud"].to_numpy() for d in (train_df, valid_df, test_df))
    print(f"train {len(X_train):,} | valid {len(X_valid):,} | test {len(X_test):,} | "
          f"fraud rate {df['is_fraud'].mean():.2%}")

    reference = X_train[DRIFT_COLUMNS].sample(min(p["reference_sample"], len(X_train)), random_state=seed)
    session = uuid.uuid4().hex[:8]

    for name, hp in p["models"].items():
        with mlflow.start_run(run_name=f"{name}-{session}"):
            mlflow.set_tags({
                "training_session": session, "model_type": name, "use_case": "airport-fraud",
                "data_version": data_version(), "git_commit": git_commit(),
            })
            mlflow.log_params({"model_type": name, **hp, "features": ",".join(MODEL_FEATURES),
                               "feature_service": FEATURE_SERVICE, "train_rows": len(X_train)})
            mlflow.log_input(mlflow.data.from_pandas(train_df, name="airport-transactions", targets="is_fraud"),
                             context="training")

            pipe = build_pipeline(name, hp, seed).fit(X_train, y_train)

            threshold = best_threshold(y_valid, pipe.predict_proba(X_valid)[:, 1])
            proba = pipe.predict_proba(X_test)[:, 1]
            pred = (proba >= threshold).astype(int)
            metrics = {
                "test_roc_auc": roc_auc_score(y_test, proba),
                "test_pr_auc": average_precision_score(y_test, proba),
                "test_precision": precision_score(y_test, pred, zero_division=0),
                "test_recall": recall_score(y_test, pred, zero_division=0),
                "test_f1": f1_score(y_test, pred, zero_division=0),
            }
            mlflow.log_param("decision_threshold", round(threshold, 4))
            mlflow.log_metrics(metrics)

            fig, ax = plt.subplots(figsize=(4, 4))
            ConfusionMatrixDisplay.from_predictions(y_test, pred, display_labels=["legit", "fraud"], ax=ax)
            ax.set_title(name)
            mlflow.log_figure(fig, "confusion_matrix.png")
            plt.close(fig)

            with tempfile.TemporaryDirectory() as tmp:
                ref_path = Path(tmp) / "reference.parquet"
                reference.to_parquet(ref_path, index=False)
                mlflow.log_artifact(str(ref_path), artifact_path="reference")

            mlflow.sklearn.log_model(
                pipe, artifact_path="model",
                signature=infer_signature(X_test, proba),
                input_example=X_test.head(3),
            )
            print(f"{name:<24} " + "  ".join(f"{k[5:]}={v:.3f}" for k, v in metrics.items())
                  + f"  threshold={threshold:.3f}")

    print(f"\nTraining session {session} done. Compare runs at {config.MLFLOW_TRACKING_URI.replace('mlflow:5000', 'localhost:5001')}")


if __name__ == "__main__":
    main()

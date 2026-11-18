"""Feature contract shared by training and serving (avoids training/serving skew).

A model input row = transaction fields (from the Kafka event)
                  + passenger profile features (from Feast)
                  + derived features (computed here, identically everywhere).
"""

import pandas as pd

FEATURE_SERVICE = "fraud_model_v1"

TXN_NUMERIC = ["amount", "hour_of_day", "is_international", "card_present", "minutes_to_departure"]
TXN_CATEGORICAL = ["merchant_category"]
FEAST_FEATURES = ["avg_amount_30d", "txn_count_7d", "distinct_airports_30d", "account_age_days"]
DERIVED = ["amount_to_avg_ratio"]

NUMERIC_FEATURES = TXN_NUMERIC + FEAST_FEATURES + DERIVED
MODEL_FEATURES = NUMERIC_FEATURES + TXN_CATEGORICAL

# Used when Feast has no profile yet (brand-new passenger)
FEAST_DEFAULTS = {"avg_amount_30d": 0.0, "txn_count_7d": 0.0, "distinct_airports_30d": 0.0, "account_age_days": 0.0}

# Columns monitored by Evidently for data drift
DRIFT_COLUMNS = TXN_NUMERIC + FEAST_FEATURES + TXN_CATEGORICAL


def build_model_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Raw transaction + Feast columns -> exact model input, in a fixed column order."""
    out = df.copy()
    for col, default in FEAST_DEFAULTS.items():
        out[col] = pd.to_numeric(out.get(col), errors="coerce").fillna(default)
    out["amount_to_avg_ratio"] = out["amount"] / (out["avg_amount_30d"] + 1.0)
    out[NUMERIC_FEATURES] = out[NUMERIC_FEATURES].astype("float64")
    out[TXN_CATEGORICAL] = out[TXN_CATEGORICAL].astype(str)
    return out[MODEL_FEATURES]

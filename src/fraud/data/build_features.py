"""DVC stage `features`: raw transactions -> Feast offline source + training events.

Outputs
  feature_repo/data/passenger_features.parquet  daily passenger profile snapshots
                                                 (Feast offline store, materialized to Redis)
  data/processed/training_events.parquet         labelled transactions = Feast entity dataframe

Each snapshot at day D only uses transactions *before* D, so a point-in-time
join in Feast never leaks future information into training.
"""

import pandas as pd

from fraud import config


def passenger_snapshots(txns: pd.DataFrame, passengers: pd.DataFrame) -> pd.DataFrame:
    txns = txns.assign(day=txns["event_timestamp"].dt.normalize())
    first_day, last_day = txns["day"].min(), txns["day"].max() + pd.Timedelta(days=1)
    snapshots = []
    for day in pd.date_range(first_day + pd.Timedelta(days=1), last_day, freq="D"):
        last_30d = txns[(txns["day"] >= day - pd.Timedelta(days=30)) & (txns["day"] < day)]
        last_7d = last_30d[last_30d["day"] >= day - pd.Timedelta(days=7)]
        snap = pd.DataFrame({"passenger_id": passengers["passenger_id"]}).set_index("passenger_id")
        snap["avg_amount_30d"] = last_30d.groupby("passenger_id")["amount"].mean()
        snap["txn_count_7d"] = last_7d.groupby("passenger_id").size()
        snap["distinct_airports_30d"] = last_30d.groupby("passenger_id")["airport"].nunique()
        snap = snap.fillna({"txn_count_7d": 0, "distinct_airports_30d": 0}).reset_index()
        age_at_end = passengers.set_index("passenger_id")["account_age_days"]
        snap["account_age_days"] = (age_at_end - (last_day - day).days).clip(lower=0).to_numpy()
        snap["event_timestamp"] = day
        snapshots.append(snap)

    features = pd.concat(snapshots, ignore_index=True)
    features["created_timestamp"] = pd.Timestamp.now(tz="UTC")
    features["avg_amount_30d"] = features["avg_amount_30d"].astype("float32")
    for col in ["txn_count_7d", "distinct_airports_30d", "account_age_days"]:
        features[col] = features[col].astype("int64")
    return features


def main() -> None:
    p = config.params()["data"]
    txns = pd.read_parquet(config.RAW_TRANSACTIONS)
    passengers = pd.read_parquet(config.PASSENGER_PROFILES)

    features = passenger_snapshots(txns, passengers)
    config.PASSENGER_FEATURES.parent.mkdir(parents=True, exist_ok=True)
    features.to_parquet(config.PASSENGER_FEATURES, index=False)
    print(f"passenger feature snapshots: {len(features):,} -> {config.PASSENGER_FEATURES}")

    cutoff = txns["event_timestamp"].min().normalize() + pd.Timedelta(days=p["warmup_days"])
    events = txns[txns["event_timestamp"] >= cutoff].drop(columns=["airport"])
    config.TRAINING_EVENTS.parent.mkdir(parents=True, exist_ok=True)
    events.to_parquet(config.TRAINING_EVENTS, index=False)
    print(f"training events: {len(events):,} (after {cutoff.date()}) -> {config.TRAINING_EVENTS}")


if __name__ == "__main__":
    main()

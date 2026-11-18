"""DVC stage `generate`: historical airport transactions -> data/raw/*.parquet"""

import numpy as np
import pandas as pd

from fraud import config
from fraud.simulation import make_passengers, make_transactions


def main() -> None:
    p = config.params()["data"]
    rng = np.random.default_rng(p["seed"])
    passengers = make_passengers(p["n_passengers"], p["seed"])

    # History ends at today's midnight (UTC) so the latest feature snapshot is fresh.
    end = pd.Timestamp.now(tz="UTC").normalize()
    start = end - pd.Timedelta(days=p["history_days"])
    n = p["txn_per_day"] * p["history_days"]
    offsets = np.sort(rng.uniform(0, (end - start).total_seconds(), n))
    timestamps = start + pd.to_timedelta(offsets, unit="s")

    txns = make_transactions(passengers, timestamps, rng)

    config.RAW_TRANSACTIONS.parent.mkdir(parents=True, exist_ok=True)
    passengers.to_parquet(config.PASSENGER_PROFILES, index=False)
    txns.to_parquet(config.RAW_TRANSACTIONS, index=False)
    print(f"passengers: {len(passengers):,} -> {config.PASSENGER_PROFILES}")
    print(f"transactions: {len(txns):,} ({start.date()} .. {end.date()}), "
          f"fraud rate {txns['is_fraud'].mean():.2%} -> {config.RAW_TRANSACTIONS}")


if __name__ == "__main__":
    main()

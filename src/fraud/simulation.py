"""Airport payment simulator.

Shared by the batch generator (historical data for training) and the Kafka
producer (live stream), so both see the same passengers and the same behaviour.

Scenarios for the live stream:
  normal  - same distribution as the training data
  drift   - holiday season: bigger baskets, more foreign travellers, night flights
            (data drift - Evidently should flag it)
  attack  - a card-testing ring hits the airports (fraud rate jumps)
"""

import uuid

import numpy as np
import pandas as pd

AIRPORTS = {
    "LIS": "PT", "OPO": "PT", "MAD": "ES", "BCN": "ES",
    "LHR": "GB", "CDG": "FR", "FRA": "DE", "AMS": "NL", "DXB": "AE", "JFK": "US",
}
MERCHANTS = [
    "airline_ticket", "duty_free", "currency_exchange", "lounge",
    "food_beverage", "car_rental", "electronics",
]
# How much each merchant type multiplies a passenger's typical spend
MERCHANT_SPEND = np.array([6.0, 1.5, 3.0, 0.8, 0.3, 4.0, 5.0])
LEGIT_MERCHANT_P = np.array([0.12, 0.25, 0.06, 0.07, 0.40, 0.05, 0.05])
FRAUD_MERCHANT_P = np.array([0.28, 0.10, 0.25, 0.02, 0.05, 0.05, 0.25])

SCENARIOS = ("normal", "drift", "attack")

# (fraud prob. for a normal passenger, fraud prob. for a compromised card)
FRAUD_P = {"normal": (0.008, 0.25), "drift": (0.008, 0.25), "attack": (0.12, 0.70)}


def make_passengers(n: int, seed: int) -> pd.DataFrame:
    """Static passenger population. Same seed -> same passengers everywhere."""
    rng = np.random.default_rng(seed)
    codes = list(AIRPORTS)
    home_airport = rng.choice(codes, n, p=_home_airport_p(codes))
    return pd.DataFrame({
        "passenger_id": np.arange(1, n + 1),
        "home_airport": home_airport,
        "home_country": [AIRPORTS[a] for a in home_airport],
        "typical_spend": rng.lognormal(mean=3.6, sigma=0.5, size=n).round(2),  # ~ EUR 40
        "account_age_days": rng.integers(5, 3000, n),  # at the end of history
        "travel_freq": rng.gamma(2.0, 1.0, n),
        "compromised": rng.random(n) < 0.05,  # stolen / skimmed cards
    })


def _home_airport_p(codes: list[str]) -> np.ndarray:
    weights = np.array([3.0 if AIRPORTS[c] == "PT" else 1.0 for c in codes])
    return weights / weights.sum()


def make_transactions(
    passengers: pd.DataFrame,
    timestamps: pd.DatetimeIndex | list,
    rng: np.random.Generator,
    scenario: str = "normal",
) -> pd.DataFrame:
    """One transaction per timestamp, vectorised."""
    n = len(timestamps)
    p_travel = passengers["travel_freq"] / passengers["travel_freq"].sum()
    pax = passengers.iloc[rng.choice(len(passengers), n, p=p_travel)].reset_index(drop=True)

    p_normal, p_compromised = FRAUD_P[scenario]
    is_fraud = rng.random(n) < np.where(pax["compromised"], p_compromised, p_normal)

    codes = np.array(list(AIRPORTS))
    random_airport = rng.choice(codes, n)
    stays_home = rng.random(n) < (0.25 if scenario == "drift" else 0.6)
    airport = np.where(~is_fraud & stays_home, pax["home_airport"], random_airport)
    is_international = (np.array([AIRPORTS[a] for a in airport]) != pax["home_country"]).astype(int)

    merchant_idx = np.where(
        is_fraud,
        rng.choice(len(MERCHANTS), n, p=FRAUD_MERCHANT_P),
        rng.choice(len(MERCHANTS), n, p=LEGIT_MERCHANT_P),
    )
    amount = pax["typical_spend"].to_numpy() * MERCHANT_SPEND[merchant_idx] * rng.lognormal(0, 0.6, n)
    amount = np.where(is_fraud, amount * rng.uniform(2.5, 8.0, n), amount)

    legit_hour = rng.normal(13, 4.5, n)
    fraud_hour = np.where(rng.random(n) < 0.4, rng.uniform(0, 6, n), rng.uniform(0, 24, n))
    hour = np.where(is_fraud, fraud_hour, legit_hour)

    card_present = (rng.random(n) < np.where(is_fraud, 0.35, 0.9)).astype(int)
    minutes_to_departure = np.where(is_fraud, 15 + rng.exponential(45, n), 20 + rng.gamma(3.0, 50.0, n))

    if scenario == "drift":
        amount = amount * 2.2
        hour = hour + 6
        minutes_to_departure = minutes_to_departure * 0.5

    # ~0.5% noisy labels: disputed chargebacks that were actually legit
    label = is_fraud | (rng.random(n) < 0.005)

    return pd.DataFrame({
        "transaction_id": [str(uuid.UUID(int=int(x))) for x in rng.integers(0, 2**63, n)],
        "passenger_id": pax["passenger_id"].to_numpy(),
        "event_timestamp": pd.to_datetime(timestamps, utc=True),
        "airport": airport,
        "merchant_category": np.array(MERCHANTS)[merchant_idx],
        "amount": np.round(amount, 2),
        "hour_of_day": np.floor(hour % 24).astype(int),
        "is_international": is_international,
        "card_present": card_present,
        "minutes_to_departure": np.round(minutes_to_departure, 1),
        "is_fraud": label.astype(int),
    })

"""Feast definitions for the airport fraud lab (`feast apply` registers them)."""

from datetime import timedelta

from feast import Entity, FeatureService, FeatureView, Field, FileSource, ValueType
from feast.types import Float32, Int64

passenger = Entity(
    name="passenger",
    join_keys=["passenger_id"],
    value_type=ValueType.INT64,
    description="Card holder paying at one of our airports",
)

passenger_profile_source = FileSource(
    name="passenger_profile_source",
    path="data/passenger_features.parquet",  # produced and versioned by the DVC `features` stage
    timestamp_field="event_timestamp",
    created_timestamp_column="created_timestamp",
)

passenger_profile = FeatureView(
    name="passenger_profile",
    entities=[passenger],
    ttl=timedelta(days=2),  # daily snapshots: a point-in-time join may look back up to 2 days
    schema=[
        Field(name="avg_amount_30d", dtype=Float32, description="Mean amount spent in the last 30 days"),
        Field(name="txn_count_7d", dtype=Int64, description="Transactions in the last 7 days"),
        Field(name="distinct_airports_30d", dtype=Int64, description="Distinct airports used in 30 days"),
        Field(name="account_age_days", dtype=Int64, description="Days since the card/account was opened"),
    ],
    online=True,
    source=passenger_profile_source,
    tags={"team": "fraud", "use_case": "airport"},
)

# The exact feature set the model consumes - used by training AND serving.
fraud_model_v1 = FeatureService(name="fraud_model_v1", features=[passenger_profile])

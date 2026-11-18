#!/usr/bin/env bash
# Step 7 - call the scoring API directly (no Kafka). Passenger features come from Feast.
set -euo pipefail
API=${API:-http://localhost:8000}
pretty() { if command -v jq >/dev/null; then jq .; else cat; echo; fi; }

echo "▶ Legit: passenger 42 buys a coffee at Lisbon airport, card present, 2h before departure"
curl -s -X POST "$API/predict" -H 'Content-Type: application/json' -d '{
  "passenger_id": 42, "airport": "LIS", "merchant_category": "food_beverage",
  "amount": 6.80, "hour_of_day": 10, "is_international": 0, "card_present": 1,
  "minutes_to_departure": 125
}' | pretty

echo
echo "▶ Suspicious: same passenger, EUR 2,400 currency exchange in Dubai at 3am, card not present, 20 min to departure"
curl -s -X POST "$API/predict" -H 'Content-Type: application/json' -d '{
  "passenger_id": 42, "airport": "DXB", "merchant_category": "currency_exchange",
  "amount": 2400, "hour_of_day": 3, "is_international": 1, "card_present": 0,
  "minutes_to_departure": 20
}' | pretty

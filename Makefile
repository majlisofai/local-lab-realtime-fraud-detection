# Absolute repo path: Prefect flows run `docker compose` from inside a container (step 9)
export LAB_HOST_DIR := $(CURDIR)

COMPOSE  := docker compose
PROFILES := --profile jobs --profile serve --profile stream --profile automate
JOB      := $(COMPOSE) run --rm trainer
CONSUMERS ?= 3

.DEFAULT_GOAL := help
.PHONY: help build up ingest train publish serve predict stream logs alerts scale \
        scenario-normal scenario-drift scenario-attack drift-report automate console fonts diagrams docs docs-all \
        docs-open status urls down clean

help: ## Show the lab steps
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# ── Step 3: infrastructure ───────────────────────────────────────────────
.env:
	@cp .env.example .env
	@sed -i.bak "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$$(openssl rand -hex 12)/; s/^GRAFANA_ADMIN_PASSWORD=.*/GRAFANA_ADMIN_PASSWORD=$$(openssl rand -hex 8)/" .env && rm -f .env.bak
	@echo "Created .env with random passwords (git-ignored)"

build: .env ## Build the app + MLflow images (uv-based)
	$(COMPOSE) $(PROFILES) build

up: .env ## Start Kafka, Redis, MLflow, Prometheus, Grafana, exporters
	$(COMPOSE) up -d --wait kafka redis postgres mlflow kafka-ui prometheus grafana kafka-exporter redis-exporter cadvisor
	$(COMPOSE) up kafka-init
	@$(MAKE) --no-print-directory urls

# ── Step 4: ingest (DVC + Feast) ─────────────────────────────────────────
ingest: ## Generate parquet data with DVC, push to remote, register + materialize Feast features
	$(JOB) sh -c 'uv run dvc repro && uv run dvc push \
	  && cd feature_repo && uv run feast apply \
	  && uv run feast materialize 2020-01-01T00:00:00 $$(date -u +%Y-%m-%dT%H:%M:%S)'
	@echo "\nCommit the data version:  git add dvc.lock && git commit -m 'data: new version'"

# ── Step 5: train (MLflow tracking) ──────────────────────────────────────
train: ## Train 3 candidate models from the Feast offline store, tracked in MLflow
	$(JOB) uv run python -m fraud.training.train

# ── Step 6: publish (MLflow registry) ────────────────────────────────────
publish: ## Quality gate -> register best run -> alias @champion
	$(JOB) uv run python -m fraud.training.publish

# ── Step 7: serve ────────────────────────────────────────────────────────
serve: ## Start the FastAPI scoring service (loads @champion)
	$(COMPOSE) --profile serve up -d --wait api
	@curl -s localhost:8000/model; echo

predict: ## Send a legit and a suspicious transaction to the API
	@./scripts/predict.sh

# ── Step 8: real-time fraud detection with Kafka ─────────────────────────
stream: ## Start the airport payment simulator (producer) and fraud consumer
	$(COMPOSE) --profile serve --profile stream up -d producer consumer

logs: ## Follow producer + consumer logs
	$(COMPOSE) --profile serve --profile stream logs -f --tail 20 producer consumer

alerts: ## Read the fraud alerts topic straight from Kafka
	$(COMPOSE) exec kafka /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server kafka:9092 \
	  --topic airport.fraud-alerts --property print.key=true --from-beginning --max-messages 10

scale: ## Scale out consumers (CONSUMERS=3) - Kafka rebalances the 3 partitions
	$(COMPOSE) --profile serve --profile stream up -d --no-recreate --scale consumer=$(CONSUMERS) consumer

# ── Monitoring scenarios ─────────────────────────────────────────────────
scenario-normal: ## Simulator: normal traffic
	@echo normal > control/scenario && echo "scenario -> normal"
scenario-drift: ## Simulator: holiday season (data drift)
	@echo drift > control/scenario && echo "scenario -> drift"
scenario-attack: ## Simulator: card-testing attack (fraud spike)
	@echo attack > control/scenario && echo "scenario -> attack"
drift-report: ## Open the latest Evidently HTML report
	@open reports/drift_report.html 2>/dev/null || echo "reports/drift_report.html (after the first $${DRIFT_WINDOW:-200} transactions)"

# ── Step 9: automate (Prefect + Alertmanager + lab console) ─────────────
automate: ## Start Prefect (UI :4200), flow runner, Alertmanager and the live lab console (:8090)
	$(COMPOSE) --profile automate up -d --wait prefect-server prefect-flows lab-console alertmanager
	@curl -s -X POST localhost:9090/-/reload >/dev/null || true
	@echo "\n  Lab console  http://localhost:8090   <- run each stage and watch the architecture"
	@echo "  Prefect UI   http://localhost:4200\n"

console: ## Open the live lab console
	@open http://localhost:8090 2>/dev/null || echo "http://localhost:8090"

# ── Brand: diagrams + docs (BRAND=majlisofai | aurora) ──────────────────
BRAND ?= majlisofai
BRANDS := $(notdir $(patsubst %/brand.json,%,$(wildcard brand/*/brand.json)))
check-brand = @echo " $(BRANDS) " | grep -q " $(BRAND) " || { echo "BRAND must be one of: $(BRANDS)"; exit 1; }
GEN = uv run --no-project python docs/diagrams

fonts: ## Fetch the brand fonts (OFL, Google Fonts) for the headless draw.io export
	@uv run --no-project python scripts/fetch_fonts.py

diagrams: fonts ## Regenerate the README diagrams in BRAND (default majlisofai) and export PNG
	$(check-brand)
	$(GEN)/generate_archimate.py --brand $(BRAND)
	$(GEN)/generate_tutorial.py --brand $(BRAND)
	@scripts/export_drawio.sh docs/diagrams
	@scripts/export_drawio.sh docs/images

docs: fonts ## Build the HTML docs site in BRAND=majlisofai|aurora -> site/<brand>/index.html
	$(check-brand)
	@rm -rf build/$(BRAND) && mkdir -p build/$(BRAND)
	$(GEN)/generate_archimate.py --brand $(BRAND) --out build/$(BRAND)
	$(GEN)/generate_tutorial.py --brand $(BRAND) --out build/$(BRAND)
	@scripts/export_drawio.sh build/$(BRAND)
	uv run --no-project --with markdown==3.7 python scripts/build_docs.py --brand $(BRAND) --images build/$(BRAND)
	@echo "\n  open site/$(BRAND)/index.html   (make docs-open BRAND=$(BRAND))\n"

docs-all: ## Build the docs site in every brand
	@for b in $(BRANDS); do $(MAKE) --no-print-directory docs BRAND=$$b || exit 1; done

docs-open: ## Open the built docs site for BRAND
	@open site/$(BRAND)/index.html 2>/dev/null || echo "site/$(BRAND)/index.html"

# ── Housekeeping ─────────────────────────────────────────────────────────
status: ## Show running containers
	$(COMPOSE) $(PROFILES) ps

urls: ## Print the lab URLs
	@echo ""
	@echo "  Kafka UI     http://localhost:8080"
	@echo "  MLflow       http://localhost:5001"
	@echo "  Fraud API    http://localhost:8000/docs"
	@echo "  Prometheus   http://localhost:9090"
	@echo "  Grafana      http://localhost:3000   (login: GRAFANA_ADMIN_USER / GRAFANA_ADMIN_PASSWORD in .env)"
	@echo "  cAdvisor     http://localhost:8081"
	@echo "  Prefect      http://localhost:4200   (after make automate)"
	@echo "  Lab console  http://localhost:8090   (after make automate)"
	@echo "  Alertmanager http://localhost:9093   (after make automate)"
	@echo ""

down: ## Stop everything (keeps data volumes)
	$(COMPOSE) $(PROFILES) down

clean: ## Stop everything and delete volumes, generated data and reports
	$(COMPOSE) $(PROFILES) down -v
	rm -rf data/raw/*.parquet data/processed/*.parquet feature_repo/data/*.parquet feature_repo/data/registry.db \
	  dvc-storage reports/*.html control/scenario

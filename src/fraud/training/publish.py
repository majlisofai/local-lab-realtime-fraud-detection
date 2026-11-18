"""Step 6 - Publish: best run -> MLflow Model Registry -> alias @champion.

Quality gate: the candidate must beat `publish.min_metric` and the current
champion. The old champion keeps the alias @previous, so a rollback is one
alias change. The serving API is told to hot-reload the new champion.
"""

import argparse

import mlflow
import requests
from mlflow.exceptions import MlflowException
from mlflow.tracking import MlflowClient

from fraud import config


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="publish even if not better than the champion")
    parser.add_argument("--no-reload", action="store_true", help="don't ask the serving API to reload")
    args = parser.parse_args()

    p = config.params()["publish"]
    name, alias, metric = p["model_name"], p["alias"], p["metric"]
    mlflow.set_tracking_uri(config.MLFLOW_TRACKING_URI)
    client = MlflowClient()

    experiment = client.get_experiment_by_name(config.params()["train"]["experiment"])
    if experiment is None:
        raise SystemExit("No experiment found - run `make train` first.")
    runs = client.search_runs([experiment.experiment_id], filter_string="attributes.status = 'FINISHED'",
                              order_by=[f"metrics.{metric} DESC"], max_results=1)
    if not runs:
        raise SystemExit("No finished training runs found.")
    best = runs[0]
    score = best.data.metrics[metric]
    print(f"best run: {best.info.run_name} ({best.info.run_id[:8]})  {metric}={score:.4f}")

    if score < p["min_metric"]:
        raise SystemExit(f"Quality gate failed: {metric}={score:.4f} < {p['min_metric']}. Not publishing.")

    try:
        champion = client.get_model_version_by_alias(name, alias)
    except MlflowException:
        champion = None
    if champion:
        if champion.run_id == best.info.run_id:
            print(f"Run is already {name}@{alias} (v{champion.version}). Nothing to do.")
            return
        champion_score = client.get_run(champion.run_id).data.metrics.get(metric, 0.0)
        print(f"current champion: v{champion.version}  {metric}={champion_score:.4f}")
        if score <= champion_score and not args.force:
            print("Candidate is not better than the champion - keeping v"
                  f"{champion.version}. Use --force to publish anyway.")
            return

    version = mlflow.register_model(f"runs:/{best.info.run_id}/model", name)
    client.update_model_version(
        name, version.version,
        description=f"{best.data.tags.get('model_type')} | {metric}={score:.4f} | "
                    f"data {best.data.tags.get('data_version')} | git {best.data.tags.get('git_commit')}",
    )
    for key in ("model_type", "data_version", "git_commit"):
        client.set_model_version_tag(name, version.version, key, best.data.tags.get(key, ""))
    client.set_model_version_tag(name, version.version, metric, f"{score:.4f}")
    if champion:
        client.set_registered_model_alias(name, "previous", champion.version)
    client.set_registered_model_alias(name, alias, version.version)
    print(f"Published {name} v{version.version} as @{alias}")

    if args.no_reload:
        return
    try:
        r = requests.post(f"{config.FRAUD_API_URL}/reload", timeout=60)
        print(f"Serving API reloaded: {r.json()}")
    except requests.RequestException:
        print("Serving API not running yet - it will load @champion on start.")


if __name__ == "__main__":
    main()

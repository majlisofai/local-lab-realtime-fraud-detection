# One image, many roles: trainer (DVC/Feast/MLflow jobs), api, producer, consumer,
# and for step 9: prefect-server, prefect-flows, lab-console.
# Dependencies are installed with uv from the committed uv.lock (reproducible builds).
FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /uvx /bin/
# docker CLI + compose plugin: lets the Prefect flows start the API / stream containers (step 9)
COPY --from=docker:27.3.1-cli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=docker:27.3.1-cli /usr/local/libexec/docker/cli-plugins/docker-compose /usr/local/libexec/docker/cli-plugins/docker-compose

# git: DVC needs it to version data alongside the code
RUN apt-get update \
    && apt-get install -y --no-install-recommends git curl \
    && rm -rf /var/lib/apt/lists/* \
    && git config --system --add safe.directory '*'

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_FROZEN=1 \
    PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    LAB_ROOT=/workspace \
    FEAST_USAGE=False \
    MPLBACKEND=Agg

WORKDIR /workspace

# 1) third-party dependencies (cached layer, rebuilt only when uv.lock changes)
COPY pyproject.toml uv.lock .python-version README.md ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --no-install-project

# 2) the lab's own code
COPY src ./src
COPY feature_repo ./feature_repo
COPY params.yaml ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync

CMD ["uv", "run", "python", "-c", "print('choose a role: api | producer | consumer | trainer')"]

# syntax=docker/dockerfile:1
# Image d'inférence : construction figée par uv.lock, SOCLE D'EXÉCUTION SEUL. Les
# bibliothèques d'analyse (SHAP, XGBoost, Optuna, matplotlib, CodeCarbon) servent à produire
# le dossier d'étude, pas à répondre à une requête — elles sont écartées et leur absence est
# vérifiée dans l'image.

# --- Construction : venv résolu par uv, groupes d'analyse exclus ---------------
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS build
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

# Dépendances d'abord (couche cachable tant que le verrou ne change pas), projet ensuite.
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-default-groups --no-dev --no-install-project
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-default-groups --no-dev

# Contrôle DANS l'image : aucune bibliothèque d'analyse ne doit avoir été tirée.
RUN /app/.venv/bin/python -c "import importlib.util as u; \
m=[x for x in ['shap','xgboost','optuna','matplotlib','codecarbon'] if u.find_spec(x)]; \
assert not m, f'libs d analyse presentes: {m}'; print('socle verifie: aucune lib d analyse')"

# --- Exécution : image mince, venv copié, compte non privilégié -----------------
FROM python:3.13-slim-bookworm AS runtime
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1
RUN groupadd --system app && useradd --system --gid app --home-dir /app app

COPY --from=build /app/.venv /app/.venv
COPY src ./src
# L'artefact modèle n'est pas dans l'image de base : il est monté à l'exécution (compose) ou
# ajouté au §10 (`COPY artifacts ./artifacts`). Sans lui, /ready répond 503 sans empêcher le démarrage.

USER app
EXPOSE 8000
CMD ["uvicorn", "decrochage_l1.serving.api:app", "--host", "0.0.0.0", "--port", "8000"]

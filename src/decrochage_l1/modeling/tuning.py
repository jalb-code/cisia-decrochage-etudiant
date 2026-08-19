"""Réglage des hyperparamètres par recherche Optuna, budget borné et pruning.

Le module porte le *verbe* - orchestrer la recherche, pas la décrire : l'espace de
recherche (quoi régler, dans quelles bornes) et le pipeline à régler sont **passés par le
notebook**, où ils se défendent. On n'y trouve donc aucune table d'hyperparamètres.

La recherche est frugale par construction : échantillonneur TPE (seed fixé, donc
reproductible), *pruning* médian qui coupe les essais mal partis, et double borne de budget
(`n_trials` **et** `timeout`). Le score est calculé pli par pli sur la même validation
croisée qu'en §8 - aucune fuite, le préprocesseur étant refité dans le pipeline à chaque pli.
"""

import json
from collections.abc import Callable
from pathlib import Path

import numpy as np
import optuna
from sklearn.base import clone
from sklearn.metrics import get_scorer
from sklearn.pipeline import Pipeline


def optuna_search(
    build_pipeline: Callable[[dict], Pipeline],
    suggest: Callable[[optuna.Trial], dict],
    X,
    y,
    cv,
    *,
    scoring: str,
    n_trials: int,
    timeout: float | None = None,
    seed: int = 0,
    direction: str = "maximize",
    n_startup_trials: int = 5,
    n_warmup_steps: int = 1,
) -> tuple[dict, optuna.Study]:
    """Cherche les meilleurs hyperparamètres d'un pipeline par validation croisée.

    `suggest(trial)` propose un jeu de paramètres (défini au notebook) ; `build_pipeline`
    en fabrique le pipeline à évaluer. Le score d'un essai est la moyenne du critère
    `scoring` sur les plis de `cv` ; il est reporté pli par pli pour permettre au pruner
    d'abandonner tôt un essai visiblement mauvais.

    Renvoie `(best_params, study)` - les paramètres retenus et l'étude complète (utile pour
    tracer le budget réellement consommé et les essais élagués).
    """
    scorer = get_scorer(scoring)
    sampler = optuna.samplers.TPESampler(seed=seed)
    pruner = optuna.pruners.MedianPruner(
        n_startup_trials=n_startup_trials, n_warmup_steps=n_warmup_steps
    )
    study = optuna.create_study(direction=direction, sampler=sampler, pruner=pruner)

    def objective(trial: optuna.Trial) -> float:
        params = suggest(trial)
        pipe = build_pipeline(params)
        scores: list[float] = []
        # Score pli par pli : on reporte la moyenne courante pour laisser le pruner
        # couper un essai qui traîne sous la médiane des essais déjà vus.
        for step, (tr, va) in enumerate(cv.split(X, y)):
            fold = clone(pipe)
            fold.fit(X.iloc[tr], y.iloc[tr])
            scores.append(scorer(fold, X.iloc[va], y.iloc[va]))
            trial.report(float(np.mean(scores)), step)
            if trial.should_prune():
                raise optuna.TrialPruned()
        return float(np.mean(scores))

    study.optimize(objective, n_trials=n_trials, timeout=timeout)
    return study.best_params, study


def pruned_ratio(study: optuna.Study) -> float:
    """Part des essais élagués - mesure directe de l'économie apportée par le pruning."""
    states = [t.state for t in study.trials]
    pruned = sum(s == optuna.trial.TrialState.PRUNED for s in states)
    return pruned / len(states) if states else 0.0


def load_cache(path: str | Path) -> dict:
    """Charge le cache de réglage (JSON) s'il existe, sinon un dictionnaire vide."""
    path = Path(path)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def cached_search(
    path: str | Path, key: str, compute: Callable[[], dict], *, use_cache: bool
) -> dict:
    """Renvoie l'entrée `key` du cache, ou exécute `compute()` puis l'y écrit (write-through).

    Sert l'exécution rapide du notebook sans relancer la recherche : un run complet
    (`use_cache=False`) mesure et persiste le résultat ; un run rapide (`use_cache=True`) le
    recharge tel quel. Si la clé manque au cache, on calcule quand même - repli sûr, jamais
    d'échec faute de cache. Optuna étant seedé, un recalcul rend les mêmes paramètres : le
    cache économise du temps, il ne fige aucun jugement (que le notebook seul porte).

    `compute` doit renvoyer un dict **JSON-sérialisable** (hyperparamètres, scalaires) ; les
    objets lourds (étude Optuna, pipeline) restent au notebook, reconstruits depuis ces valeurs.
    """
    path = Path(path)
    cache = load_cache(path)
    if use_cache and key in cache:
        return cache[key]
    result = compute()
    cache[key] = result
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    return result

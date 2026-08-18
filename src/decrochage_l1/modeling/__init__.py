"""Modélisation du décrochage — protocole, préprocesseur, familles, évaluation, ablation.

Ce sous-package porte le **verbe** de la modélisation (§8-§9) : comment splitter,
préparer, entraîner, mesurer, ablater. Il **ne porte aucun jugement** — quelles
colonnes, quelle famille, quel seuil : ces choix se décident dans le notebook, à la
section où la mesure les fonde, et lui sont passés en paramètre.

- `protocol`      : split scellé + validation croisée (le protocole d'évaluation, C5) ;
- `preprocessing` : le préprocesseur appris (imputation, encodage, scaling), refit par pli ;
- `families`      : les familles de modèles candidates, chacune dans un `Pipeline` ;
- `evaluation`    : les mesures (métriques, prédictions out-of-fold, courbes) ;
- `ablation`      : le coût du retrait d'un bloc de features (minimisation, §8.6).
"""

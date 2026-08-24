"""Mise en forme des livrables de reporting (export Excel du récapitulatif des métriques).

Ce qu'il fait : le *comment* de la présentation - disposition des feuilles, en-têtes groupés
fusionnés, formats numériques, statut coloré. Ce qu'il ne fait pas : aucun calcul de métrique ni
aucun *jugement* sur les configurations (quel modèle, quel jeu, quelle note) - cela reste au
notebook, qui passe à ce module un `DataFrame` déjà constitué et la disposition à appliquer.
"""

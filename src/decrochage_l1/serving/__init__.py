"""Couche de service (§10-§13) : ce qui sert le modèle, mesure et explique — hors notebook.

Sous-package **runtime** : il n'importe rien de l'outillage d'analyse (SHAP, Optuna,
matplotlib…), pour rester dans l'empreinte de l'image d'inférence. Il porte le *verbe* —
comment charger, valider, prédire, expliquer, mesurer la dérive — ; le *complément* (bornes,
seuils, thèmes, exclusions) lui est **passé en paramètre**, déclaré au notebook et sérialisé
dans la fiche du modèle, jamais codé en dur ici.
"""

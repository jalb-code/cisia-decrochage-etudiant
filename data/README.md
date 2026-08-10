# Données — approvisionnement

Les fichiers de données **ne sont pas versionnés** — précaution RGPD : un fichier entré dans l'historique Git y demeure. La règle porte sur `data/` **entier**, paliers produits par le code compris. Seule la structure des dossiers est conservée via `.gitkeep`.

## Arborescence attendue

```
data/
├── raw/      # dataset brut à déposer ici (non versionné)
│   ├── dataset decrochage_etudiants_complet_V5.csv   (5 240 lignes / 5 200 étudiants, 33 colonnes)
│   └── dataset catalogue_formations_V5.csv           (jointure via `filiere`)
├── sample/   # échantillon 50 lignes (non versionné)
│   └── dataset decrochage_etudiants_echantillon_V5.csv
├── bronze/   # PRODUIT par le code — ne rien déposer à la main
├── silver/   # idem
└── gold/     # idem
```

## Les paliers

`raw` et `sample` sont une **zone de dépôt** : jamais modifiées. Les trois paliers qui suivent sont **produits par le code**, chacun n'ajoutant qu'une transformation — pour qu'une anomalie constatée en aval se rattache à une étape précise.

| Palier | Ce que le palier ajoute | Produit par |
|---|---|---|
| **bronze** | Écritures conformées, vocabulaire recodé, lignes strictement identiques retirées — **aucune information perdue** | [`data/bronze.py`](../src/decrochage_l1/data/bronze.py) |
| **silver** | Manquants et exclusions tranchés et appliqués | à venir |
| **gold** | Jeu prêt à l'apprentissage, features finales comprises | à venir |

Les paliers s'écrivent en **CSV**, lisibles dans un tableur. Ces fichiers sont des **copies de contrôle** : le notebook, lui, fait circuler les `DataFrame` d'une section à l'autre. Relire un palier avec `pandas` seul ne rendrait ni les dates ni les entiers *nullable* posés à la conformation — il faut alors le reprofiler (`profiling.profile_csv` puis `conform`), comme on charge une source brute.

## Comment obtenir les données

Récupérer les fichiers bruts (source du projet de certification) et les déposer dans `data/raw/` et `data/sample/` en respectant les noms ci-dessus (espaces inclus). Rien d'autre n'est à déposer à la main : le reste de `data/` est produit par le code.

Les rapports de profilage HTML atterrissent dans `reports/`, hors dépôt pour la même raison que `data/` : ils citent des valeurs brutes.
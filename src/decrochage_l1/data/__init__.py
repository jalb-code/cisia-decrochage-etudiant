"""Sous-package `data` — mesurer un fichier de données, et uniformiser l'écriture de ses valeurs.

- `profiling` : ce qu'un CSV contient et comment c'est écrit — encodage, délimiteur,
  type de chaque colonne, motifs d'écriture, manquants, non-conformité ;
- `profiling_report` : la restitution HTML du profil, mise en page seule ;
- `cleaning` : les primitives de mise en forme (parsing, normalisation d'écriture)
  sur lesquelles `profiling` s'appuie.

Aucun de ces modules ne décide quoi que ce soit du jeu de données : ils mesurent
et mettent en forme, ils ne retirent rien et ne recodent rien.
"""

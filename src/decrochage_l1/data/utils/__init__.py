"""Briques **agnostiques** du cas d'usage — mesurer et mettre en forme, sans rien décider.

Aucun module d'ici ne connaît une colonne, une modalité ou une borne du projet : ils
reçoivent tout en paramètre et rendent un résultat.

- `cleaning_utils` : primitives de mise en forme d'une `Series` (parsing, normalisation
  d'écriture) - pures, insensibles à l'ordre et à la taille du lot ;
- `profiling_utils` : ce qu'un CSV contient et comment c'est écrit (encodage, délimiteur,
  types, motifs, manquants), plus les contrôles qui confrontent le jeu à une déclaration
  **reçue en paramètre**. Il mesure, il ne transforme pas ;
- `profiling_report` : la restitution HTML du profil, mise en page seule ;
- `recoding_utils` : le **mécanisme** de recodage (synonymes ramenés à une forme
  canonique), qui reçoit son `vocabulary` et n'en fige aucun.

La connaissance métier - vocabulaire cible, conformation du jeu du projet - vit dans
`data.preparation`, qui orchestre ces briques.
"""

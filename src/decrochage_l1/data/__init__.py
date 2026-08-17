"""Sous-package `data` — mesurer un fichier, le profiler, le mettre en forme.

Deux niveaux, une séparation nette entre l'agnostique et le métier :

- `utils` : briques **agnostiques** du cas d'usage - mesure (`profiling_utils`),
  primitives (`cleaning_utils`), restitution HTML (`profiling_report`) et mécanisme de
  recodage (`recoding_utils`). Elles reçoivent tout en paramètre, ne décident de rien ;
- `preparation` : **spécifique au cas d'usage** - le vocabulaire cible
  (`CANONICAL_MODALITIES`) et la mise en forme du jeu (`conform`, `transform` :
  conformation, recodage, doublons exacts retirés). C'est lui qui orchestre les briques
  de `utils`. `transform` sert deux fois : au jeu de travail de §5, puis au palier de §7.

Le **bronze** n'a pas de module : c'est la copie exacte des fichiers reçus, et une copie
ne se code pas. Aucun de ces modules ne décide de ce qui entrera dans le modèle - ces
décisions se prennent au notebook, à l'endroit où la mesure les fonde, et s'appliquent
aux paliers suivants.
"""

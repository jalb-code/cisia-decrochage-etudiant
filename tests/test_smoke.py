"""Test de fumée du bootstrap projet.

But : garantir que le package s'importe correctement et que la CI collecte au moins
un test (sinon `pytest` renvoie l'exit code 5 « no tests collected » et échoue).
"""

import decrochage_l1


def test_package_importable():
    """Le package s'importe et expose une version non vide."""
    assert decrochage_l1.__version__

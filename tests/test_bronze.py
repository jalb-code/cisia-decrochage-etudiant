import pandas as pd

from decrochage_l1 import schema
from decrochage_l1.data import bronze, profiling


def _build(tmp_path, content: str) -> tuple[pd.DataFrame, bronze.BronzeResult]:
    """Produit un bronze depuis un CSV écrit à la volée ; rend le jeu et le compte."""
    source = tmp_path / "source.csv"
    source.write_text(content, encoding="utf-8")
    return bronze.build(profiling.profile_csv(source), tmp_path / "bronze.csv")


def test_les_lignes_strictement_identiques_sont_retirees(tmp_path):
    data, result = _build(tmp_path, "id,note\na,12\nb,15\na,12\n")
    assert (result.n_rows_source, result.n_duplicates_removed, result.n_rows) == (3, 1, 2)
    assert len(data) == 2


def test_le_dedoublonnage_suit_la_conformation(tmp_path):
    """Deux lignes qui ne diffèrent que par l'écriture sont des jumelles une fois conformées."""
    _, result = _build(tmp_path, "filiere,n\n Gestion ,1\nGESTION,1\ndroit,2\n")
    assert result.n_duplicates_removed == 1


def test_le_dedoublonnage_suit_aussi_le_recodage(tmp_path):
    """Deux libellés synonymes rendent identiques des lignes qui ne l'étaient pas."""
    data, result = _build(tmp_path, "sexe,age\nF,20\nFemme,20\nH,21\n")
    assert result.n_duplicates_removed == 1
    assert sorted(data["sexe"]) == ["femme", "homme"]


def test_le_recodage_ramene_les_synonymes_a_la_forme_canonique(tmp_path):
    data, result = _build(
        tmp_path,
        "sexe,bac_type,mention_bac,boursier\nNB,GEN,ab,O\nnr,Technologique,tb,0\n",
    )
    assert list(data["sexe"]) == ["autre", "inconnu"]  # identité déclarée ≠ non-réponse
    assert list(data["bac_type"]) == ["general", "technologique"]
    assert list(data["mention_bac"]) == ["assez bien", "tres bien"]
    assert list(data["boursier"]) == ["oui", "non"]
    assert set(result.recoded_columns) == {"sexe", "bac_type", "mention_bac", "boursier"}


def test_une_modalite_hors_vocabulaire_reste_intacte(tmp_path):
    """Le recodage n'invente rien : une valeur inattendue doit rester visible."""
    data, _ = _build(tmp_path, "sexe,n\nF,1\nmartien,2\n")
    assert sorted(data["sexe"]) == ["femme", "martien"]


def test_aucune_colonne_ni_valeur_porteuse_d_information_n_est_perdue(tmp_path):
    data, result = _build(tmp_path, "id,note,constante\na,12,x\nb,,x\n")
    assert (result.n_columns, result.n_rows) == (3, 2)
    assert list(data.columns) == ["id", "note", "constante"]
    assert data["note"].isna().sum() == 1  # un manquant reste manquant : aucune imputation
    assert data["constante"].nunique() == 1  # une variance nulle n'est pas un motif de retrait


def test_le_fichier_ecrit_est_une_copie_du_jeu_rendu(tmp_path):
    data, result = _build(tmp_path, "id,note\na,12\nb,15\n")
    assert result.destination.exists()
    assert len(pd.read_csv(result.destination)) == len(data)


def test_le_vocabulaire_cible_est_declare_en_forme_normalisee():
    """Clés et cibles viennent de `normalize_text` : minuscules, sans accent."""
    for groupes in schema.CANONICAL_MODALITIES.values():
        for canonique, variantes in groupes.items():
            assert canonique == canonique.lower()
            assert all(variante == variante.lower() for variante in variantes)


def test_les_sources_du_projet_sont_declarees_une_seule_fois():
    assert set(bronze.SOURCES) == {"etudiants", "catalogue"}
    assert all(name.endswith(".csv") for name in bronze.SOURCES.values())

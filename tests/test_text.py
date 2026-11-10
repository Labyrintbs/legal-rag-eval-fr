from legalrag.text import context_of


def test_context_is_the_last_four_section_levels_cut_to_120_characters():
    path = " > ".join(["Partie", "Livre IV : Travailleurs à domicile", "Titre II", "Chapitre II", "x" * 200])
    context = context_of(path)
    assert context.split(" > ")[0] == "Livre IV : Travailleurs à domicile"
    assert len(context.split(" > ")) == 4 and context.endswith("x" * 120)
    assert context_of("CHAPITRE VIII : Voies de recours") == "CHAPITRE VIII : Voies de recours"

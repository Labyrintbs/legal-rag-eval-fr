import pytest

from legalrag import questiongen as qg

BODY = (
    "En cas de démission, l'existence et la durée du préavis sont fixées par la loi, "
    "ou par convention ou accord collectif de travail."
)


def question(text, answer="Par la loi ou une convention."):
    return {"question": text, "reponse_courte": answer}


def test_the_prompt_files_are_well_formed():
    writer = qg.load_prompts(qg.PROMPTS / "question_writer.yaml")
    families = ["plain", "lay"]
    assert set(writer["styles"]) == {f"{f}.v{n}" for f in families for n in (1, 2, 3)} | {"conditions.v1"}
    assert writer["styles"]["conditions.v1"]["context"]
    assert "JSON" in writer["base"]
    assert writer["styles"]["plain.v1"]["max_overlap"] is None
    assert writer["styles"]["lay.v3"]["context"] and not writer["styles"]["lay.v2"].get("context")
    reviewers = qg.load_prompts(qg.PROMPTS / "question_reviewer.yaml")["reviewers"]
    assert set(reviewers) == {f"reviewer.v{n}" for n in (1, 2, 3, 4, 5)}
    for reviewer in reviewers.values():  # every checked field is one the prompt asks the model for
        assert all(field in reviewer["system"] for field in reviewer["checks"])
    assert all("unsure" in r["system"] for r in reviewers.values())
    assert reviewers["reviewer.v2"]["context"] and not reviewers["reviewer.v1"]["context"]


def test_the_writer_sees_the_body_and_the_context_only_for_styles_that_ask_for_it():
    writer = qg.load_prompts(qg.PROMPTS / "question_writer.yaml")
    system, user = qg.writer_messages(writer, "lay.v2", BODY, "Livre IV : Travailleurs à domicile")
    assert system["content"] == writer["base"]
    assert BODY in user["content"] and "AUCUN terme" in user["content"]
    assert "Travailleurs à domicile" not in user["content"]
    scoped = qg.writer_messages(writer, "lay.v3", BODY, "Livre IV : Travailleurs à domicile")[1]
    assert "Contexte : Livre IV : Travailleurs à domicile" in scoped["content"]
    assert qg.prompt_hash(writer, "lay.v2") != qg.prompt_hash(writer, "plain.v2")
    assert qg.prompt_hash(writer, "lay.v3") != qg.prompt_hash(writer, "lay.v2")


def test_the_reviewer_gets_the_context_only_in_v2():
    reviewers = qg.load_prompts(qg.PROMPTS / "question_reviewer.yaml")
    q = question("Qui décide ?")
    v1 = qg.reviewer_messages(reviewers, "reviewer.v1", "lay.v3", BODY, "Chapitre V", q)[1]["content"]
    v2 = qg.reviewer_messages(reviewers, "reviewer.v2", "lay.v3", BODY, "Chapitre V", q)[1]["content"]
    assert "Contexte" not in v1 and "Contexte : Chapitre V" in v2
    assert "Style demandé : lay" in v2 and "Question : Qui décide ?" in v2


def test_context_is_the_last_four_section_levels_cut_to_120_characters():
    path = " > ".join(["Partie", "Livre IV : Travailleurs à domicile", "Titre II", "Chapitre II", "x" * 200])
    context = qg.context_of(path)
    assert context.split(" > ")[0] == "Livre IV : Travailleurs à domicile"
    assert len(context.split(" > ")) == 4 and context.endswith("x" * 120)
    assert qg.context_of("CHAPITRE VIII : Voies de recours") == "CHAPITRE VIII : Voies de recours"


def test_parse_json_refuses_text_and_non_objects():
    assert qg.parse_json('{"question": "a"}') == {"question": "a"}
    with pytest.raises(ValueError, match="not valid JSON"):
        qg.parse_json("Voici la question")
    with pytest.raises(TypeError, match="not an object"):
        qg.parse_json("[1]")


def test_overlap_ignores_accents_and_short_words():
    assert qg.overlap("Quel préavis en cas de démission ?", BODY) == 1.0
    assert qg.overlap("Je veux partir, je dois prévenir ?", BODY) == 0.0
    assert qg.overlap("", BODY) == 0.0


def test_review_problems_come_from_the_checks_not_only_from_the_verdict():
    checks = {"answerable_from_article": True, "compound": False}
    good = {"verdict": "accept", "answerable_from_article": True, "compound": False}
    assert qg.review_problems(good, checks) == []
    assert qg.review_problems({**good, "compound": True}, checks) == ["compound"]
    assert qg.review_problems({**good, "verdict": "unsure"}, checks) == ["verdict unsure"]
    assert qg.review_problems({"verdict": "accept", "compound": False}, checks) == [
        "missing answerable_from_article"
    ]
    assert qg.review_problems({"error": "not valid JSON"}, checks) == ["review failed"]
    assert qg.review_problems(None, checks) == ["review failed"]


def test_a_good_lay_question_has_no_flag():
    assert qg.automatic_checks(question("Si je pars, qui décide du délai ?"), BODY, 0.5, []) == []


def test_each_automatic_check_flags_its_case():
    def flags(text, max_overlap=0.5, earlier=()):
        return qg.automatic_checks(question(text), BODY, max_overlap, list(earlier))

    assert flags("Que dit l'article L1237-1 ?") == ["cites an article number"]
    assert flags("Que dit l'article 17 ?") == ["cites an article number"]
    assert "copies the article wording" in flags("Le préavis de démission est-il fixé par la loi ?")[0]
    assert flags("Le préavis de démission est-il fixé par la loi ?", max_overlap=None) == []
    assert flags("Quoi ? Et alors ?") == ["several questions or too long"]
    assert flags("Qui décide du délai, et combien de temps dure-t-il ?") == [
        "compound question (two ideas)"
    ]
    assert flags("Peut-on suivre un bilan et est-il payé ?") == ["compound question (two ideas)"]
    assert flags(" ".join(["mot"] * 36) + " ?") == ["several questions or too long"]
    assert flags(" ".join(["mot"] * 34) + " ?") == []
    assert flags("Qui décide du délai et du lieu ?") == []
    assert flags("Qui décide du délai ?", earlier=["Qui décide donc du délai ?"]) == [
        "near duplicate of an earlier question"
    ]
    assert qg.automatic_checks({"question": "", "reponse_courte": "x"}, BODY, 0.5, []) == [
        "missing question or short answer"
    ]

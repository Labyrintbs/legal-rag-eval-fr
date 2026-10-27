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
    assert set(writer["styles"]) == {"plain.v1", "lay.v1", "plain.v2", "lay.v2"}
    assert "JSON" in writer["base"]
    assert writer["styles"]["plain.v1"]["max_overlap"] is None
    reviewer = qg.load_prompts(qg.PROMPTS / "question_reviewer.yaml")
    assert reviewer["id"] == "reviewer.v1" and "unsure" in reviewer["system"]


def test_the_writer_sees_the_article_body_and_the_style_only():
    writer = qg.load_prompts(qg.PROMPTS / "question_writer.yaml")
    system, user = qg.writer_messages(writer, "lay.v1", BODY)
    assert system["content"] == writer["base"]
    assert BODY in user["content"] and "AUCUN terme" in user["content"]
    assert qg.prompt_hash(writer, "lay.v1") != qg.prompt_hash(writer, "plain.v1")


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
    assert flags(" ".join(["mot"] * 31) + " ?") == ["several questions or too long"]
    assert flags("Qui décide du délai et du lieu ?") == []
    assert flags("Qui décide du délai ?", earlier=["Qui décide donc du délai ?"]) == [
        "near duplicate of an earlier question"
    ]
    assert qg.automatic_checks({"question": "", "reponse_courte": "x"}, BODY, 0.5, []) == [
        "missing question or short answer"
    ]

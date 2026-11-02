import json
from pathlib import Path

import httpx
import pytest

from legalrag import headsentence
from legalrag.models import Article
from legalrag.questiongen import load_prompts

PROMPT = load_prompts(Path("prompts/heading_sentence.yaml"))["prompts"]["sentence.v1"]


def article(uid, source="code_travail", kind="article", num="L1221-13", body="Le contrat est écrit.", path="Partie > Livre > Titre"):
    return Article(uid=uid, source_code=source, lang="fr", kind=kind, native_id=uid, article_num=num, section_path=path,
                   body_text=body, content_hash=uid, source_url="x")


def test_sample_is_the_same_for_the_same_seed_and_has_the_planned_counts():
    pool = [article(f"ct{i}") for i in range(30)] + [article(f"ra{i}", "rgpd", "article", str(i)) for i in range(6)] \
        + [article(f"rr{i}", "rgpd", "recital", str(i)) for i in range(6)] + [article(f"an{i}", kind="annex") for i in range(4)]
    plan = (("code_travail", "article", 5), ("rgpd", "article", 2), ("rgpd", "recital", 2), ("code_travail", "annex", 1))
    first = headsentence.sample(pool, 7, plan)
    assert [a.uid for a in first] == [a.uid for a in headsentence.sample(list(reversed(pool)), 7, plan)]
    assert [a.uid for a in first] != [a.uid for a in headsentence.sample(pool, 8, plan)]
    assert [(a.source_code, a.kind) for a in first].count(("code_travail", "article")) == 5 and len(first) == 10


def test_the_prompt_shows_the_text_and_the_section_but_not_the_article_number():
    chat = headsentence.messages(PROMPT, article("a", num="L1221-13", body="x" * 9000, path="A > B > C > D > E"))
    scope, body = chat[1]["content"].split("Texte de l'article :")
    assert "L1221-13" not in chat[1]["content"] and "C > D > E" in scope and "B > C" not in scope
    assert body.strip() == "x" * PROMPT["max_body_chars"] and chat[0]["role"] == "system"


def test_a_missing_section_path_is_named():
    assert "(non indiqué)" in headsentence.messages(PROMPT, article("a", path=""))[1]["content"]


@pytest.mark.parametrize("answer, sentence, flags", [
    ('« Le salarié peut demander une copie de son contrat. »', "Le salarié peut demander une copie de son contrat.", []),
    ("Une phrase.\nUne autre ligne.", "Une phrase.", ["several_lines"]),
    ("", "", ["empty"]),
    ("Voir l'article L1221-13 pour le contrat.", "Voir l'article L1221-13 pour le contrat.", ["article_number"]),
    (" ".join(["mot"] * 50), " ".join(["mot"] * 50), ["too_long"]),
])
def test_clean(answer, sentence, flags):
    assert headsentence.clean(answer, 45) == (sentence, flags)


def test_ask_local_posts_one_chat_with_thinking_off_and_returns_usage_and_timings():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"], seen["body"] = request.url.path, json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "Une phrase."}}],
                                         "usage": {"completion_tokens": 4}, "timings": {"predicted_per_second": 30.0}})

    http = httpx.Client(base_url="http://server", transport=httpx.MockTransport(handler))
    out = headsentence.ask_local(http, "m", [{"role": "user", "content": "q"}], 120)
    assert seen["url"] == "/v1/chat/completions" and seen["body"]["temperature"] == 0
    assert seen["body"]["chat_template_kwargs"] == {"enable_thinking": False} and seen["body"]["max_tokens"] == 120
    assert out["text"] == "Une phrase." and out["usage"] == {"completion_tokens": 4} and out["timings"]["predicted_per_second"] == 30.0

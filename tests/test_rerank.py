from legalrag import evaluate, gold, rerank


class Scorer:
    """Scores a chunk by the number written after 'score' in its text; records what it was given."""

    def __init__(self):
        self.pairs = []

    def score(self, pairs):
        self.pairs += pairs
        return [float(text.split("score")[1]) for _, text in pairs]


class Conn:
    def __init__(self, rows):
        self.rows, self.args = rows, None

    def execute(self, sql, args):
        self.args = args
        return self

    def fetchall(self):
        return self.rows


def test_chunk_texts_asks_for_the_stored_keys_and_returns_texts_by_label():
    conn = Conn([("code_travail", "article", "L1", "t1"), ("rgpd", "article", "17", "t17"),
                 ("rgpd", "recital", "65", "t65"), ("code_travail", "article", "L1", "t1b")])
    texts = rerank.chunk_texts(conn, 3, "fr", ["L1", "art 17", "rct 65"])
    assert conn.args == (3, "fr", ["code_travail|article|L1", "rgpd|article|17", "rgpd|recital|65"])
    assert texts == {"L1": ["t1", "t1b"], "art 17": ["t17"], "rct 65": ["t65"]}


def test_articles_are_ordered_by_their_best_chunk_and_ties_keep_the_first_order(monkeypatch):
    texts = {"A": ["score1"], "B": ["score5", "score2"], "C": ["score1"], "D": []}
    monkeypatch.setattr(rerank, "chunk_texts", lambda *args: texts)
    candidates = [("A", "ha"), ("B", "hb"), ("C", "hc"), ("D", "hd")]
    scorer = Scorer()
    ranked = rerank.rerank(None, 1, "fr", "question", candidates, scorer, keep=3)
    assert ranked == [("B", "hb"), ("A", "ha"), ("C", "hc")]
    assert [text for _, text in scorer.pairs] == ["score1", "score5", "score2", "score1"]
    assert all(question == "question" for question, _ in scorer.pairs)


def test_an_article_without_text_goes_last(monkeypatch):
    monkeypatch.setattr(rerank, "chunk_texts", lambda *args: {"B": ["score0"]})
    ranked = rerank.rerank(None, 1, "fr", "q", [("A", "ha"), ("B", "hb")], Scorer(), keep=2)
    assert [label for label, _ in ranked] == ["B", "A"]


def test_the_rerank_search_reorders_dense_candidates_to_the_top_20(monkeypatch):
    seen = {}
    monkeypatch.setattr(evaluate, "retrieve", lambda conn, run, lang, v, keep: seen.update(depth=keep) or [("A", "ha")])
    monkeypatch.setattr(evaluate.rerank, "rerank",
                        lambda conn, run, lang, text, candidates, scorer, keep: seen.update(keep=keep) or [("Z", "hz")])
    question = gold.GoldQuestion(id="a", question="q", lang="fr", group="A", kind="unanswerable", gold=[], split="dev",
                                 provenance=gold.Provenance(method="hand_written"))
    out = evaluate.retrieve_all(None, 1, [question], [None], "rerank", scorer=Scorer(), rerank_depth=30)
    assert out == {"a": [("Z", "hz")]} and seen == {"depth": 30, "keep": 20}

import json

from legalrag.evaluation import claimrag

DATA = {"input_data": [
    {"query_id": 7, "query": "q", "relevant_chunk": "Article 8 text.", "gt_answer": "a", "claims": [
        {"claim": ["GDPR", "ensures", "free movement"], "claim_correctness": "Correct", "claim_entailment": "Entailment"},
        {"claim": ["GDPR", "aims", "privacy"], "claim_correctness": "Correct", "claim_entailment": "Neutral"},
        {"claim": ["x", "y", "z"], "claim_correctness": "Correct", "claim_entailment": "Doesn't Make Sense"},
        {"claim": ["a", "b", "c"], "claim_correctness": "", "claim_entailment": ""},
        {"claim": ["Transfer", "relates to", "many people"], "claim_correctness": "Incorrect", "claim_entailment": "Contradiction"}]}]}


def test_only_claims_with_a_usable_expert_label_are_loaded_with_their_chunk(tmp_path):
    path = tmp_path / "claims.json"
    path.write_text(json.dumps(DATA))
    triples = claimrag.load_claims(path)
    assert [(t.key, t.label) for t in triples] == [("7|0", "Entailment"), ("7|1", "Neutral"), ("7|4", "Contradiction")]
    assert triples[0].parts == ("GDPR", "ensures", "free movement") and triples[0].chunk == "Article 8 text."


def test_the_claim_file_may_be_a_bare_list_of_items(tmp_path):
    path = tmp_path / "claims.json"
    path.write_text(json.dumps(DATA["input_data"]))
    assert len(claimrag.load_claims(path)) == 3


def test_the_rag_file_chunk_replaces_the_claim_chunk_where_the_question_text_matches_whatever_the_id(tmp_path):
    claims = tmp_path / "claims.json"
    claims.write_text(json.dumps([
        {"query_id": 1, "query": "Same?", "relevant_chunk": "short", "claims": [
            {"claim": ["a", "b", "c"], "claim_entailment": "Entailment"}]},
        {"query_id": 31, "query": "Shifted id?", "relevant_chunk": "short", "claims": [
            {"claim": ["d", "e", "f"], "claim_entailment": "Neutral"}]},
        {"query_id": 3, "query": "Only here?", "relevant_chunk": "short", "claims": [
            {"claim": ["g", "h", "i"], "claim_entailment": "Neutral"}]}]))
    rag = tmp_path / "rag.json"
    rag.write_text(json.dumps({"input_data": [
        {"query_id": 1, "query": "Same?", "relevant_chunk": "a much longer chunk"},
        {"query_id": 30, "query": "Shifted id?", "relevant_chunk": "another long chunk"}]}))
    kept = claimrag.with_rag_chunks(claimrag.load_claims(claims), rag)
    assert [(t.key, t.chunk) for t in kept] == [("1|0", "a much longer chunk"), ("31|0", "another long chunk")]


def test_clean_chunk_drops_markdown_and_separators_but_keeps_the_paragraphs():
    assert claimrag.clean_chunk("**Title**\n\n1. First.\n\n---\n\n#### 2. Second.\n") == "Title\n1. First.\n2. Second."


def test_questions_take_the_rag_chunk_by_text_the_kind_and_the_expert_entailed_claims_only(tmp_path):
    claims = tmp_path / "claims.json"
    claims.write_text(json.dumps([
        {"query_id": 1, "query": "Same?", "relevant_chunk": "short", "claims": [
            {"claim": ["a", "has", "b"], "claim_entailment": "Entailment"},
            {"claim": ["c", "has", "d"], "claim_entailment": "Neutral"}]},
        {"query_id": 2, "query": "Empty?", "relevant_chunk": "", "claims": []},
        {"query_id": 3, "query": "Only here?", "relevant_chunk": "own chunk", "claims": []}]))
    rag = tmp_path / "rag.json"
    rag.write_text(json.dumps({"input_data": [
        {"query_id": 9, "query": "Same?", "relevant_chunk": "**long** chunk", "question_category": "False Premise"}]}))
    questions = claimrag.load_questions(claims, rag)
    assert [(q.id, q.chunk, q.kind, q.reference_claims) for q in questions] == [
        (1, "long chunk", "false_premise", ["A has b."]), (3, "own chunk", "answerable", [])]


ARTICLE_8 = "Where the child is below the age of sixteen years processing shall be lawful only if consent is given by the holder."
ARTICLE_6 = "Processing shall be lawful only if at least one of the following applies and to the extent that it applies."


def test_gold_labels_keep_the_articles_that_overlap_the_chunk_and_drop_the_ones_with_a_stray_phrase():
    chunk = f"Article 8 Conditions for a child's consent. {ARTICLE_8} Member States may provide a lower age."
    assert claimrag.gold_labels(chunk, [("art 8", ARTICLE_8), ("art 6", ARTICLE_6)]) == ["art 8"]
    assert claimrag.gold_labels("", [("art 8", ARTICLE_8)]) == []


def test_completeness_counts_the_reference_claims_the_answer_covers_per_question_and_overall():
    rows = [{"id": 1, "outcome": "answered", "text": "Quatre mois. [1]\n\n[1] L1 - Quatre mois.", "reference_claims": ["A.", "B."]},
            {"id": 2, "outcome": "answered", "text": "Une règle. [1]\n\n[1] L2 - Une règle.", "reference_claims": ["C."]},
            {"id": 3, "outcome": "refused_by_model", "text": "", "reference_claims": ["D."]}]
    items = claimrag.completeness_items(rows)
    assert [i.key for i in items] == ["1|ref0", "1|ref1", "2|ref0"] and items[0].passages == [("answer", "Quatre mois.")]
    verdicts = [{"key": "1|ref0", "label": "supported"}, {"key": "1|ref1", "label": "partly"},
                {"key": "2|ref0", "label": "not supported"}]
    c = claimrag.completeness(rows, verdicts)
    assert (c["questions"], c["reference_claims"], c["covered"], c["covered_or_partly"]) == (2, 3, 1, 2)
    assert c["claim_recall"] == 1 / 3 and c["mean_per_question"] == (0.5 + 0.0) / 2


def test_retrieval_counts_hits_recall_and_rank_of_the_gold_articles_and_groups_by_gold_list():
    rows = [{"gold": ["art 8"], "top5": ["art 6", "art 8"]}, {"gold": ["art 8"], "top5": ["art 6"]},
            {"gold": ["art 49", "rct 112"], "top5": ["art 49", "rct 1"]}, {"gold": [], "top5": ["art 1"]}]
    r = claimrag.retrieval(rows)
    assert r["questions"] == 3 and r["hit_at_5"] == 2 / 3 and r["recall_at_5"] == (1 + 0 + 0.5) / 3
    assert r["mrr_at_5"] == (0.5 + 0 + 1) / 3
    assert r["per_gold"] == {"art 8": [1, 2], "art 49 + rct 112": [1, 1]}


def test_pick_pairs_takes_the_wanted_count_per_judge_label_one_per_question_first():
    items = [claimrag.claimjudge.Item(f"{q}|ref{i}", "c", [("answer", "a")], "") for q in range(1, 7) for i in range(2)]
    labels = ["supported", "supported", "partly", "partly", "not supported", "not supported"] * 2
    verdicts = [{"key": i.key, "label": label} for i, label in zip(items, labels, strict=True)]
    picked = claimrag.pick_pairs(items, verdicts, {"supported": 2, "partly": 1, "not supported": 1})
    got = {i.key: next(v["label"] for v in verdicts if v["key"] == i.key) for i in picked}
    assert sorted(got.values()) == ["not supported", "partly", "supported", "supported"]
    assert len({k.split("|")[0] for k in got}) == 4  # no question twice while others are available
    assert [i.key for i in claimrag.pick_pairs(items, verdicts, {"supported": 2})] == [i.key for i in claimrag.pick_pairs(items, verdicts, {"supported": 2})]


def test_the_coverage_sheet_shows_the_claim_and_the_answer_but_no_judge_label():
    from legalrag.evaluation import labelsheet

    page = labelsheet.render_pairs([("7|ref0", "Quelle durée ?", "Four months.", "Four months.\nRenewable once.")], "t")
    assert page.count('name="7|ref0|claim0"') == 3 and "Reference claim: Four months." in page
    assert page.count("<blockquote>") == 2 and "covered" in page


def test_the_halves_split_by_question_so_one_question_is_never_in_both():
    assert claimrag.half("8|0") == claimrag.half("8|3") == "dev" and claimrag.half("7|2") == "test"


def test_the_template_joins_the_three_parts_into_a_sentence():
    assert claimrag.template_sentence(("article 49(1)", "regulates", "transfers to third countries")) == \
        "Article 49(1) regulates transfers to third countries."


def test_items_use_the_chunk_as_the_passage_the_two_class_label_and_skip_missing_sentences(tmp_path):
    path = tmp_path / "claims.json"
    path.write_text(json.dumps(DATA))
    triples = claimrag.load_claims(path)
    items = claimrag.to_items(triples, ["One.", None, "Three."])
    assert [(i.key, i.claim, i.human) for i in items] == [("7|0", "One.", "supported"), ("7|4", "Three.", "not supported")]
    assert items[0].passages == [("GDPR source chunk", "Article 8 text.")]
    empty = claimrag.Triple("8|0", ("a", "b", "c"), "Entailment", "  ")
    assert claimrag.to_items([empty], ["A b c."]) == []

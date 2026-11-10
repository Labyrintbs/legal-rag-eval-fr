import json

from legalrag import claimrag

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

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

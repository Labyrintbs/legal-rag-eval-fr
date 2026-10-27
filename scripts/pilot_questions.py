"""Pilot of the question writer: 3 articles x 2 styles x 2 models, reviewed by the pro model.

Default is a dry run (prints the worst-case cost, calls nothing); --run spends money, within the
caps of llm.Budget. Four planted questions on L1237-1 test whether the reviewer catches defects.
"""

import argparse
import json
import os
import sys
from pathlib import Path

from legalrag import db, llm
from legalrag import questiongen as qg

ARTICLES = [
    ("code_travail", "article", "L1237-1"),
    ("code_travail", "article", "L4121-3-1"),
    ("rgpd", "article", "17"),
]
FAMILIES = ["plain", "lay"]
WRITER, REVIEWER = "deepseek-flash", "deepseek-v4-pro"
COMPARED = "deepseek-v4-pro"
WRITER_MAX_TOKENS, REVIEWER_MAX_TOKENS = 400, 300
OUT = Path("data/pilot")

PLANTED = [
    ("not_in_article", "plain", "Quel est le montant de l'indemnité de licenciement ?", "Elle dépend de l'ancienneté."),
    ("copies_wording", "lay", "Le préavis de démission est-il fixé par la loi ou par convention ou accord collectif ?", "Oui."),
    ("invented_fact", "plain", "Pourquoi le préavis de démission est-il de trois mois pour un cadre ?", "Parce que la loi le prévoit."),
    ("good", "lay", "Si je démissionne, qui décide du temps de préavis ?", "La loi, une convention collective ou, à défaut, les usages."),
]


def load_article(conn, source: str, kind: str, num: str) -> str:
    row = conn.execute(
        "SELECT body_text FROM articles WHERE source_code = %s AND kind = %s AND article_num = %s"
        " AND lang = 'fr'",
        (source, kind, num),
    ).fetchone()
    return row[0]


def write_jobs(articles: dict, writer_prompts: dict, styles: list[str]) -> list[dict]:
    return [
        {"article": num, "style": style, "model": model,
         "messages": qg.writer_messages(writer_prompts, style, articles[num])}
        for num in articles for style in styles for model in (WRITER, COMPARED)
    ]


def worst_case(jobs: list[dict], max_tokens: int) -> float:
    return sum(
        llm.worst_case_cost(j["model"], llm.estimate_tokens("".join(m["content"] for m in j["messages"])), max_tokens)
        for j in jobs
    )


def run_call(http, budget, label, job, max_tokens):
    try:
        text = llm.chat(http, llm.LEDGER, budget, label, job["model"], job["messages"], max_tokens)
        return qg.parse_json(text), None
    except (ValueError, TypeError, KeyError) as error:
        return None, str(error)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true", help="spend money; default is a dry run")
    parser.add_argument("--version", default="v2", help="style version, e.g. v1 or v2")
    args = parser.parse_args()
    styles = [f"{family}.{args.version}" for family in FAMILIES]
    tag = f"pilot-{args.version}"

    writer_prompts = qg.load_prompts(qg.PROMPTS / "question_writer.yaml")
    reviewer_prompts = qg.load_prompts(qg.PROMPTS / "question_reviewer.yaml")
    with db.connect() as conn:
        articles = {num: load_article(conn, source, kind, num) for source, kind, num in ARTICLES}

    jobs = write_jobs(articles, writer_prompts, styles)
    planned_reviews = [j for j in jobs if j["model"] == WRITER]
    review_estimate = sum(
        llm.worst_case_cost(REVIEWER, llm.estimate_tokens(articles[j["article"]]) + 400, REVIEWER_MAX_TOKENS)
        for j in planned_reviews + [{"article": "L1237-1"}] * len(PLANTED)
    )
    total = worst_case(jobs, WRITER_MAX_TOKENS) + review_estimate
    print(f"{len(jobs)} writer calls + {len(planned_reviews) + len(PLANTED)} reviews; "
          f"worst case {total:.4f} USD (peak price, every input token a miss, full max_tokens)")
    if not args.run:
        return

    budget = llm.Budget(run_cap=1.0, total_cap=5.0)
    with llm.make_http(os.environ["DEEPSEEK_API_KEY"]) as http:
        llm.record_balance(llm.LEDGER, llm.balance(http), f"before-{tag}")
        records = []
        for job in jobs:
            question, error = run_call(http, budget, "pilot-writer", job, WRITER_MAX_TOKENS)
            body = articles[job["article"]]
            earlier = [r["question"]["question"] for r in records if r["article"] == job["article"] and r["question"]]
            max_overlap = writer_prompts["styles"][job["style"]]["max_overlap"]
            flags = qg.automatic_checks(question, body, max_overlap, earlier) if question else [error]
            overlap = qg.overlap(question["question"], body) if question and question.get("question") else None
            records.append({**{k: job[k] for k in ("article", "style", "model")}, "kind": "written",
                            "prompt_hash": qg.prompt_hash(writer_prompts, job["style"]),
                            "question": question, "flags": flags, "overlap": overlap})
        for name, family, text, answer in PLANTED:
            style = f"{family}.{args.version}"
            question = {"question": text, "reponse_courte": answer}
            body = articles["L1237-1"]
            records.append({"article": "L1237-1", "style": style, "model": "planted", "kind": name,
                            "question": question, "overlap": qg.overlap(text, body),
                            "flags": qg.automatic_checks(question, body, writer_prompts["styles"][style]["max_overlap"], [])})
        for record in records:
            if record["model"] not in (WRITER, "planted") or not record["question"]:
                continue
            messages = qg.reviewer_messages(reviewer_prompts, record["style"], articles[record["article"]], record["question"])
            review, error = run_call(
                http, budget, "pilot-reviewer",
                {"model": REVIEWER, "messages": messages}, REVIEWER_MAX_TOKENS,
            )
            record["review"] = review or {"error": error}
        llm.record_balance(llm.LEDGER, llm.balance(http), f"after-{tag}")

    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f"question_{tag}.json"
    out.write_text(json.dumps(records, ensure_ascii=False, indent=1))
    print(f"written {out}; spent {budget.spent:.4f} USD estimated")


if __name__ == "__main__":
    sys.exit(main())

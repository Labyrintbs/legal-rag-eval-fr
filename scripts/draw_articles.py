"""Draw the articles of one batch of model-written questions and print them for review.

Code du travail: some drawn in proportion to the number of ministry sheets citing the article
(only those cited by 2 or more), some at random from the rest. GDPR: random among the chapters that
concern people and companies. The sheets come from
https://github.com/SocialGouv/fiches-travail-data (data/fiches-travail.json), saved to
data/external/. No API call and no cost.

--previous FILE --reject ID=reason keeps the earlier draw except the rejected articles, which are
replaced from the same pool with a second seed; the rejections and their reasons are kept in the file.
"""

import argparse
import hashlib
import json
import random
from collections import Counter
from pathlib import Path

from legalrag import db, draw
from legalrag.smoke import load_questions

SEED = 20261027
MIN_SHEETS = 2
MIN_CHARS, MAX_CHARS = 150, 5000
MAX_PER_PART = 2
# GDPR chapters I-V and VIII-IX; VI, VII, X, XI (authorities, cooperation, final provisions) are
# not what a user asks about.
GDPR_ARTICLES = set(range(1, 51)) | set(range(77, 92))
# Already used by the question-writer pilot.
PILOT = {"L1237-1", "L4121-3-1", "art 17"}
OUT = Path("data/drawn")


def load_articles(conn, source: str, lang: str) -> dict[str, dict]:
    rows = conn.execute(
        "SELECT article_num, section_path, body_text FROM articles"
        " WHERE source_code = %s AND kind = 'article' AND lang = %s"
        " AND length(body_text) BETWEEN %s AND %s",
        (source, lang, MIN_CHARS, MAX_CHARS),
    ).fetchall()
    return {num: {"section_path": path, "body": body} for num, path, body in rows}


def label(source: str, article: str) -> str:
    return article if source == "code_travail" else f"art {article}"


def row(source: str, article: str, pool: str, counts: Counter, text: dict) -> dict:
    cited = counts[article] if source == "code_travail" else None
    part = draw.part_of(article) if source == "code_travail" else None
    return {"source": source, "article": article, "pool": pool, "sheets": cited, "part": part, **text}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sheets", type=Path, default=Path("data/external/fiches-travail.json"))
    parser.add_argument("--weighted", type=int, default=5)
    parser.add_argument("--random-ct", type=int, default=2)
    parser.add_argument("--gdpr", type=int, default=3)
    parser.add_argument("--name", default="batch1")
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--reject", action="append", default=[], metavar="ID=reason")
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--exclude", type=Path, nargs="*", default=[],
                        help="earlier draw files whose articles, and rejected ones, are not drawn again")
    args = parser.parse_args()

    sheets_bytes = args.sheets.read_bytes()
    counts = draw.sheet_counts(json.loads(sheets_bytes))
    with db.connect() as conn:
        ct = load_articles(conn, "code_travail", "fr")
        gdpr = load_articles(conn, "rgpd", "fr")
    gdpr = {n: a for n, a in gdpr.items() if int(n) in GDPR_ARTICLES}

    rejected = dict(item.split("=", 1) for item in args.reject)
    kept = []
    if args.previous:
        kept = [r for r in json.loads(args.previous.read_text())["articles"] if r["article"] not in rejected]
        wanted = Counter(r["pool"] if r["source"] == "code_travail" else "gdpr"
                         for r in json.loads(args.previous.read_text())["articles"]
                         if r["article"] in rejected)
        n_weighted, n_random, n_gdpr = wanted["weighted"], wanted["random"], wanted["gdpr"]
        rng = random.Random(args.seed + 1)
    else:
        n_weighted, n_random, n_gdpr = args.weighted, args.random_ct, args.gdpr
        rng = random.Random(args.seed)

    smoke = {e for q in load_questions(Path("tests/smoke_questions.yaml")) for e in q.expected}
    earlier = [json.loads(p.read_text()) for p in args.exclude]
    used = {label(r["source"], r["article"]) for d in earlier for r in d["articles"]}
    used |= {k if k.startswith(("L", "R", "D")) else f"art {k}" for d in earlier for k in d["meta"].get("rejected", {})}
    excluded = PILOT | smoke | used | set(rejected) | {f"art {a}" for a in rejected} \
        | {label(r["source"], r["article"]) for r in kept}
    ct = {n: a for n, a in ct.items() if n not in excluded}
    gdpr = {n: a for n, a in gdpr.items() if f"art {n}" not in excluded and n not in excluded}
    pool = {n: counts[n] for n in ct if counts[n] >= MIN_SHEETS}
    rest = {n: 1.0 for n in ct if n not in pool}

    taken = Counter(r["part"] for r in kept if r["part"])
    rows = list(kept)
    for n in draw.draw(rng, pool, n_weighted, taken, MAX_PER_PART):
        rows.append(row("code_travail", n, "weighted", counts, ct[n]))
    for n in draw.draw(rng, rest, n_random, taken, MAX_PER_PART):
        rows.append(row("code_travail", n, "random", counts, ct[n]))
    for n in rng.sample(sorted(gdpr), n_gdpr):
        rows.append(row("rgpd", n, "random", counts, gdpr[n]))

    OUT.mkdir(parents=True, exist_ok=True)
    meta = {"seed": args.seed, "sheets_sha256": hashlib.sha256(sheets_bytes).hexdigest(),
            "weighted_pool_size": len(pool), "random_pool_size": len(rest), "gdpr_pool_size": len(gdpr),
            "previous": str(args.previous) if args.previous else None, "rejected": rejected}
    out = OUT / f"{args.name}.json"
    out.write_text(json.dumps({"meta": meta, "articles": rows}, ensure_ascii=False, indent=1))
    print(meta)
    for r in rows[len(kept):] if args.previous else rows:
        leaf = " > ".join(r["section_path"].split(" > ")[-2:])
        print(f"\n{r['source']} {r['article']} [{r['pool']}, sheets={r['sheets']}, part={r['part']}, "
              f"{len(r['body'])} chars]\n  {leaf}\n  {r['body'][:260]}")
    print(f"\nwritten {out}: {len(rows)} articles")


if __name__ == "__main__":
    main()

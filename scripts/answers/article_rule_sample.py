"""Sample test of the article-number rule for the service (step 0f, part 3). No model call, no cost: only the search.
For 15 questions that name an article and 15 that do not, shows what the rule finds and where the intended article
stands in the top articles without and with the rule. Output: data/pilot/article_rule_sample.json and a table.
"""

import json
from pathlib import Path

from legalrag.answering import articlenum, rag, search
from legalrag.index import db, embed

RUN = "default"

# (question, intended article label or None). A label is as shown to the visitor: "L1221-13", "art 17", "rct 47".
NAMING = [
    ("Que dit l'article L1221-13 du code du travail ?", "L1221-13"),
    ("Pouvez-vous m'expliquer l'article L1232-1 ?", "L1232-1"),
    ("L1235-3 : à combien s'élève l'indemnité en cas de licenciement sans cause réelle et sérieuse ?", "L1235-3"),
    ("Que prévoit l'article L3121-27 sur la durée légale du travail ?", "L3121-27"),
    ("De quoi parle l'article L1243-11 ?", "L1243-11"),
    ("Mon contrat cite l'article L1242-2, est-ce que c'est légal pour un CDD ?", "L1242-2"),
    ("Quelle est la règle de l'article R*3231-4 ?", "R*3231-4"),
    ("Qu'est-ce que l'article R1454-14 du Code du travail ?", "R1454-14"),
    ("Que dit l'article 17 du RGPD ?", "art 17"),
    ("What does article 15 GDPR say?", "art 15"),
    ("RGPD article 33 : sous quel délai notifier une violation de données ?", "art 33"),
    ("Que dit le considérant 47 du RGPD ?", "rct 47"),
    ("Entre l'article L4121-1 et l'article L1152-1, lequel parle du harcèlement moral ?", "L1152-1"),
    ("Que dit l'article L9999-99 ?", None),  # a number that does not exist
    ("Selon l'article 17, puis-je demander l'effacement de mes données ?", None),  # bare number, no GDPR named
]
NOT_NAMING = [
    "Quelle est la durée du préavis en cas de démission ?",
    "Mon employeur peut-il refuser mes congés payés ?",
    "Combien de jours de congé après un mariage ?",
    "Quelle est la durée maximale d'un CDD de remplacement ?",
    "Puis-je être licencié pendant un arrêt maladie ?",
    "Comment calculer l'indemnité légale de licenciement ?",
    "Mon employeur peut-il lire mes e-mails professionnels ?",
    "Qu'est-ce que le droit à l'effacement dans le RGPD ?",
    "Un employeur doit-il nommer un délégué à la protection des données ?",
    "Combien de temps un employeur peut-il garder le dossier d'un candidat refusé ?",
    "Quel est le délai de prévenance pour un changement d'horaires ?",
    "Le décret 2017-1387 change-t-il le plafond des indemnités ?",
    "Mon contrat prévoit un essai de 4 mois, est-ce permis ?",
    "L'article 12 de ma convention collective prévoit 5 jours de plus, qui l'emporte ?",
    "Mon patron m'a envoyé un message à 23 h 30, dois-je répondre ?",
]


def rank_of(label: str | None, ranking: list[str]) -> int | None:
    return ranking.index(label) + 1 if label in ranking else None


def main() -> None:
    with db.connect() as conn:
        run_id = conn.execute("SELECT id FROM chunking_runs WHERE name = %s", (RUN,)).fetchone()[0]
    retriever = rag.LegalRetriever(db.connect, run_id, embed.SentenceTransformerEmbedder("cpu"), "fr")
    rows = []
    for kind, items in (("naming", NAMING), ("not naming", [(q, None) for q in NOT_NAMING])):
        for question, intended in items:
            hits = rag.hits_of(retriever.retrieve(question))
            labels = [h.label for h in hits]
            with db.connect() as conn:
                named = articlenum.lookup(conn, question, "fr")
            with_rule = [label for label, _ in articlenum.put_first(named, [(x, "") for x in labels], search.TOP_ARTICLES)]
            rows.append({"kind": kind, "question": question, "intended": intended, "named_by_rule": [n for n, _ in named],
                         "rank_without": rank_of(intended, labels), "rank_with": rank_of(intended, with_rule),
                         "changed": labels != with_rule,
                         "top_similarity": round(hits[0].similarity, 3) if hits else None, "weak": search.is_weak(hits),
                         "top_without": labels, "top_with": with_rule})
    Path("data/pilot").mkdir(parents=True, exist_ok=True)
    Path("data/pilot/article_rule_sample.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))
    for r in rows:
        print(f"{r['kind']:<10} rank {r['rank_without']!s:>4} -> {r['rank_with']!s:>4}  found {r['named_by_rule']!s:<16} "
              f"changed={r['changed']!s:<5} sim {r['top_similarity']} weak={r['weak']!s:<5} {r['question'][:50]}")


if __name__ == "__main__":
    main()

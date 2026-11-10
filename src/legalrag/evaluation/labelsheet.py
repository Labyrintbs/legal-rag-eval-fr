"""The sheet for labelling answers by hand (step 0d, judge validation): a sample of the pilot answers as one HTML
file that works offline. Per claim: is it supported by the passage it cites? Per answer: does it answer the
question, or was the refusal right? The labels are downloaded as JSON and compared with the judge later.
"""

import html
import json
import random
import re
from dataclasses import dataclass

MARKS = re.compile(r"((?:\[\d+\])+)$")
NOTE = re.compile(r"\n(?=\[\d+\] )")
GDPR = ("art ", "rct ")
SUPPORT = ("supported", "partly", "not supported")
ANSWERS = ("yes", "partly", "no")
REFUSALS = ("right", "wrong", "unsure")


@dataclass(frozen=True)
class Claim:
    text: str
    passages: list[tuple[str, str]]  # (article label, passage shown to the reader)


def parse_answer(text: str) -> list[Claim]:
    """The claims of a rendered answer with the passages they cite (see `answer.render`)."""
    head, _, tail = text.partition("\n\n")
    notes = {}
    for note in NOTE.split(tail):
        number, _, rest = note.partition("] ")
        label, _, passage = rest.partition(" - ")
        notes[int(number[1:])] = (label, passage)
    claims = []
    for line in head.split("\n"):
        marks = MARKS.search(line)
        if marks:
            numbers = [int(n) for n in re.findall(r"\d+", marks.group(1))]
            claims.append(Claim(line[:marks.start()].rstrip(), [notes[n] for n in numbers if n in notes]))
    return claims


def pick(rows: list[dict], answered: int = 19, gdpr_share: float = 0.3, seed: int = 20261109,
         skip: frozenset[str] = frozenset()) -> list[dict]:
    """Every row that is not a plain answer (refusals, false premise, underspecified), plus a random sample of the
    plain answers, about `gdpr_share` of them citing the GDPR. In the order of the input rows; `skip` leaves out
    the answers that are already labelled."""
    rows = [r for r in rows if r["id"] not in skip]
    rest = [r for r in rows if r["outcome"] != "answered" or r["kind"] in ("false_premise", "underspecified")]
    plain = [r for r in rows if r["outcome"] == "answered" and r not in rest]
    law = [r for r in plain if any(c.startswith(GDPR) for c in r["cited"])]
    code = [r for r in plain if r not in law]
    rng = random.Random(seed)
    n_law = min(len(law), round(answered * gdpr_share))
    chosen = rng.sample(law, n_law) + rng.sample(code, min(len(code), answered - n_law))
    keep = {r["id"] for r in rest + chosen}
    return [r for r in rows if r["id"] in keep]


def _radios(name: str, values: tuple[str, ...]) -> str:
    return " ".join(f'<label><input type="radio" name="{name}" value="{v}"> {v}</label>' for v in values)


def _texts(title: str, texts: list[tuple[str, str]]) -> str:
    """A collapsed block with (article label, text) pairs; nothing when there are none."""
    if not texts:
        return ""
    body = "".join(f'<blockquote><i>{html.escape(label)}</i> {html.escape(text)}</blockquote>' for label, text in texts)
    return f"<details><summary>{html.escape(title)}</summary>{body}</details>"


def _item(row: dict) -> str:
    key = html.escape(row["id"])
    gold = ", ".join(html.escape(g) for g in row["gold"]) or "none (no answer expected)"
    out = [f'<section data-id="{key}"><h2>{key} <small>{html.escape(row["kind"])}</small></h2>',
           f'<p class="q">{html.escape(row["question"])}</p>',
           f'<p class="meta">Articles in the gold list: {gold}</p>']
    if row["outcome"] == "answered":
        for i, claim in enumerate(parse_answer(row["text"])):
            out.append(f'<div class="claim"><p><b>{html.escape(claim.text)}</b></p>')
            out += [f'<blockquote><i>{html.escape(label)}</i> {html.escape(passage)}</blockquote>'
                    for label, passage in claim.passages]
            out.append(f'<p>Supported by what it cites? {_radios(f"{key}|claim{i}", SUPPORT)}</p></div>')
        out.append(f'<p>Does the answer answer the question? {_radios(f"{key}|answer", ANSWERS)}</p>')
    else:
        out.append(f'<p class="refusal">Not answered ({html.escape(row["outcome"])}): {html.escape(row["reason"] or "")}</p>')
        out.append(_texts("What the model was shown (the top 5 articles)", row.get("seen", [])))
        out.append(_texts("Text of the gold articles (what should answer it)", row.get("gold_text", [])))
        out.append(f'<p>Was refusing right? (right: what the model was shown does not answer the question; wrong: it does) '
                   f'{_radios(f"{key}|refusal", REFUSALS)}</p>')
    out.append(f'<p><input type="text" name="{key}|note" placeholder="note (optional)" size="60"></p></section>')
    return "\n".join(out)


def load_checks(path, rows: list[dict], seed: int = 20261109) -> list[dict]:
    """The claim checks (`eval/answer_checks.json`) as items for the sheet, in a shuffled order: each is a claim,
    edited or unchanged, with the passages the original claim cited. Stops if an original no longer matches."""
    by_id = {r["id"]: r for r in rows}
    items = []
    for edit in json.loads(path.read_text()):
        source = by_id[edit["from"]]
        original = parse_answer(source["text"])[edit["claim"]]
        if original.text != edit["original"]:
            raise ValueError(f"{edit['id']}: the claim {edit['from']}#{edit['claim']} is no longer the stored original")
        items.append({"id": edit["id"], "question": source["question"], "claim": Claim(edit["text"], original.passages)})
    random.Random(seed).shuffle(items)
    return items


def _check_item(item: dict) -> str:
    key, claim = html.escape(item["id"]), item["claim"]
    out = [f'<section data-id="{key}"><h2>{key} <small>claim check</small></h2>',
           f'<p class="q">{html.escape(item["question"])}</p>', '<div class="claim">', f'<p><b>{html.escape(claim.text)}</b></p>']
    out += [f'<blockquote><i>{html.escape(label)}</i> {html.escape(passage)}</blockquote>' for label, passage in claim.passages]
    out.append(f'<p>Supported by what it cites? {_radios(f"{key}|claim0", SUPPORT)}</p></div>')
    out.append(f'<p><input type="text" name="{key}|note" placeholder="note (optional)" size="60"></p></section>')
    return "\n".join(out)


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Answer labels</title>
<style>
body {{ font: 16px/1.5 system-ui, sans-serif; max-width: 52rem; margin: 2rem auto; padding: 0 1rem; }}
section {{ border-top: 3px solid #888; padding: 1rem 0; }}
.claim {{ margin: .8rem 0; padding-left: .8rem; border-left: 3px solid #bbb; }}
blockquote {{ margin: .3rem 0; padding: .3rem .6rem; background: #f2f2f2; color: #222; font-size: 14px; }}
.q {{ font-size: 1.1rem; }} .meta {{ color: #555; font-size: 14px; }} .refusal {{ color: #8a4b00; }}
label {{ margin-right: .8rem; }} button {{ font-size: 1rem; padding: .5rem 1rem; }}
#bar {{ position: sticky; top: 0; background: #fff; padding: .5rem 0; border-bottom: 1px solid #ccc; }}
@media (prefers-color-scheme: dark) {{ body {{ background: #1c1c1c; color: #eee; }} #bar {{ background: #1c1c1c; }}
blockquote {{ background: #2c2c2c; color: #eee; }} .meta {{ color: #aaa; }} .refusal {{ color: #ffb866; }} }}
</style></head><body>
<div id="bar"><b id="count"></b> <button onclick="save()">Download labels.json</button>
<small>Progress is kept in this browser; download when you finish or stop.</small></div>
{intro}
{items}
<script>
const KEY = "answer-labels-{sheet}";
const fields = () => [...document.querySelectorAll("input")];
function collect() {{
  const out = {{}};
  fields().forEach(f => {{ if ((f.type === "radio" && f.checked) || (f.type === "text" && f.value)) out[f.name] = f.value; }});
  return out;
}}
function update() {{
  const total = new Set(fields().filter(f => f.type === "radio").map(f => f.name)).size;
  const done = Object.keys(collect()).filter(k => !k.endsWith("|note")).length;
  document.getElementById("count").textContent = done + " of " + total + " labelled";
  localStorage.setItem(KEY, JSON.stringify(collect()));
}}
function save() {{
  const blob = new Blob([JSON.stringify({{sheet: "{sheet}", labels: collect()}}, null, 1)], {{type: "application/json"}});
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "labels.json"; a.click();
}}
const saved = JSON.parse(localStorage.getItem(KEY) || "{{}}");
fields().forEach(f => {{
  if (f.type === "radio" && saved[f.name] === f.value) f.checked = true;
  if (f.type === "text" && saved[f.name]) f.value = saved[f.name];
  f.addEventListener("input", update);
}});
update();
</script></body></html>
"""


INTRO = """<p>Label what the answer does with the text it cites, not whether you know the law to be true.
<b>supported</b>: the passage says it. <b>partly</b>: the passage says part of it, or says it with a condition the claim leaves out.
<b>not supported</b>: the passage does not say it.</p>"""

COVERAGE = ("covered", "partly", "not covered")
COVERAGE_INTRO = """<p>Each item has a <b>reference claim</b> (from an expert's reference answer) and <b>our answer</b> to the same
question. Does our answer say what the claim says? <b>covered</b>: yes, in the same or other words, or a reader would plainly
conclude it from our answer. <b>partly</b>: our answer says part of it, or a weaker version. <b>not covered</b>: our answer
does not say it, or says something different. Judge only against our answer, not against what you know of the law.</p>"""


def _pair_item(key: str, question: str, claim: str, answer: str) -> str:
    key = html.escape(key)
    lines = "".join(f"<blockquote>{html.escape(line)}</blockquote>" for line in answer.split("\n") if line.strip())
    return (f'<section data-id="{key}"><h2>{key} <small>coverage</small></h2><p class="q">{html.escape(question)}</p>'
            f'<p><b>Reference claim: {html.escape(claim)}</b></p><p class="meta">Our answer:</p>{lines}'
            f'<p>Does our answer say it? {_radios(f"{key}|claim0", COVERAGE)}</p>'
            f'<p><input type="text" name="{key}|note" placeholder="note (optional)" size="60"></p></section>')


def render_pairs(pairs: list[tuple[str, str, str, str]], sheet: str) -> str:
    """The sheet of (key, question, reference claim, our answer) items, for the completeness hand check."""
    return PAGE.format(items="\n".join(_pair_item(*p) for p in pairs), sheet=html.escape(sheet), intro=COVERAGE_INTRO)


def render(rows: list[dict], sheet: str, checks: list[dict] | None = None) -> str:
    items = [_item(r) for r in rows] + [_check_item(c) for c in checks or []]
    return PAGE.format(items="\n".join(items), sheet=html.escape(sheet), intro=INTRO)


def read_rows(path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

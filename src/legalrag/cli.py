from pathlib import Path

import pandas as pd
import typer

from legalrag import verify
from legalrag.ingest import build_chunks, token_counter
from legalrag.sources import legi

app = typer.Typer(no_args_is_help=True)

RAW = Path("data/raw")
PARQUET = RAW / "legi_vincegx33_train.parquet"
TOKENIZER = RAW / "bge-m3-tokenizer.json"
PROFILES = Path("docs/data_profiles")


@app.command()
def profile() -> None:
    """Write the Code du travail data profile."""
    total = len(pd.read_parquet(PARQUET, columns=["article_id"]))
    out = legi.profile(legi.read(PARQUET), TOKENIZER, total)
    (PROFILES / "code_travail.md").write_text(out)
    typer.echo(out)


@app.command("verify")
def verify_cmd() -> None:
    """Run the Code du travail checks and write the spot-check list."""
    articles = legi.to_articles(legi.read(PARQUET))
    count = token_counter(TOKENIZER)
    chunks = build_chunks(articles, count)
    typer.echo(f"{len(articles)} articles, {len(chunks)} chunks")
    results = verify.verify_legi(articles, chunks, count)
    for name, ok, detail in results:
        typer.echo(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")

    spot_file = PROFILES / "spot_check_code_travail.md"
    if spot_file.exists():  # holds the user's manual results; never overwrite
        raise typer.Exit(0 if all(ok for _, ok, _ in results) else 1)
    rows = [
        "# Spot check: Code du travail",
        "",
        "20 articles drawn with a fixed seed. Open each URL and compare number, text and place "
        "in the code with the line below. Write the result in the last column.",
        "",
        "| Article | URL | Section path (last level) | Body start | OK? |",
        "|---|---|---|---|---|",
    ]
    for a in verify.spot_check_sample(articles):
        last = a.section_path.split(" > ")[-1]
        rows.append(f"| {a.article_num} | {a.source_url} | {last} | {a.body_text[:80]} | |")
    (PROFILES / "spot_check_code_travail.md").write_text("\n".join(rows) + "\n")
    raise typer.Exit(0 if all(ok for _, ok, _ in results) else 1)

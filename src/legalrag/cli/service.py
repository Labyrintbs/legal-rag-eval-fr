"""Commands on the running service: traces, the kill switch, and the model spend."""

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated

import typer

from legalrag import llm
from legalrag.answering import cache, limits, trace
from legalrag.index import db

app = typer.Typer(no_args_is_help=True)
traces_app = typer.Typer(no_args_is_help=True, help="Look at the traces of the service: failures, summary, purge, export.")
service_app = typer.Typer(no_args_is_help=True, help="Switch the written answers of the running service on or off.")
cache_app = typer.Typer(no_args_is_help=True, help="The answer cache: purge, clear, warm.")
app.add_typer(traces_app, name="traces")
app.add_typer(service_app, name="service")
app.add_typer(cache_app, name="cache")


@traces_app.command("failures")
def traces_failures_cmd(
    days: Annotated[float, typer.Option(help="How far back to look")] = 7,
    outcome: Annotated[list[str] | None, typer.Option(help="Only these outcomes (default: all quality failures)")] = None,
    limit: Annotated[int, typer.Option(help="Most rows to print")] = 50,
) -> None:
    """The latest requests the system could not answer, with what retrieval found."""
    if bad := [o for o in outcome or [] if o not in trace.OUTCOMES]:
        raise typer.BadParameter(f"unknown outcome {bad}; choose from {', '.join(trace.OUTCOMES)}")
    with db.connect() as conn:
        rows = trace.failures(conn, timedelta(days=days), tuple(outcome or trace.FAILURES), limit)
    for r in rows:
        top = ", ".join(f"{x['label']} ({x.get('score', 0):.2f})" for x in r["retrieved"][:3])
        typer.echo(f"{r['created_at']:%Y-%m-%d %H:%M} {r['outcome']:<24} {r['question'][:90]!r}\n    top: {top or '-'}"
                   f"{'  | ' + r['refusal_reason'] if r['refusal_reason'] else ''}{'  | ' + r['error'] if r['error'] else ''}")
    typer.echo(f"{len(rows)} failures in the last {days:g} days")


@traces_app.command("feedback")
def traces_feedback_cmd(
    days: Annotated[float, typer.Option(help="How far back to look")] = 7,
    down_only: Annotated[bool, typer.Option("--down-only", help="Only the thumbs-down")] = False,
    limit: Annotated[int, typer.Option(help="Most rows to print")] = 50,
) -> None:
    """The votes of visitors (thumbs, kind, comment), newest first: the way to read what visitors say."""
    with db.connect() as conn:
        rows = trace.votes(conn, timedelta(days=days), down_only, limit)
    for r in rows:
        served = "from the cache" if r["outcome"] == "cache_hit" else r["outcome"]
        typer.echo(f"{r['created_at']:%Y-%m-%d %H:%M} {'DOWN' if r['feedback'] < 0 else 'up  '} {r['feedback_kind'] or '-':<16} "
                   f"{served:<24} {r['question'][:80]!r}" + (f"\n    comment: {r['feedback_comment']}" if r["feedback_comment"] else ""))
    typer.echo(f"{len(rows)} votes in the last {days:g} days")


@traces_app.command("summary")
def traces_summary_cmd(days: Annotated[float, typer.Option(help="How far back to look")] = 1) -> None:
    """Requests by outcome, share answered, tokens, cost and time of the answered ones."""
    with db.connect() as conn:
        s = trace.summary(conn, timedelta(days=days))
    typer.echo(f"{s['requests']} requests in the last {days:g} days; answered share "
               f"{'-' if s['answered_share'] is None else format(s['answered_share'], '.0%')}")
    for name, n in sorted(s["by_outcome"].items(), key=lambda x: -x[1]):
        typer.echo(f"  {name:<24} {n}")
    a = s["answered"]
    typer.echo(f"answered: {a['tokens_in']} tokens in, {a['tokens_out']} out, {a['cost_usd']:.4f} USD, "
               f"time median {a['p50_ms'] or 0:.0f} ms, 95th percentile {a['p95_ms'] or 0:.0f} ms")
    typer.echo(f"English translations of answers: {s['translations']['n']}, {s['translations']['cost_usd']:.4f} USD")


@traces_app.command("purge")
def traces_purge_cmd(yes: Annotated[bool, typer.Option("--yes", help="Do not ask for confirmation")] = False) -> None:
    """Erase the text of ordinary requests older than 7 days, then delete the traces past their 30-day expiry; asks first.
    Run it every hour (the schedule is a deployment task): the privacy page promises both."""
    with db.connect() as conn:
        to_erase, to_delete = trace.erasable(conn), trace.expired(conn)
        typer.echo(f"{to_erase} ordinary requests will have their text erased, {to_delete} expired traces will be deleted.")
        if (to_erase or to_delete) and not yes:
            typer.confirm("Go on?", abort=True)
        if to_erase:
            trace.scrub(conn)
        if to_delete:
            trace.purge(conn)
    typer.echo("done" if to_erase or to_delete else "nothing to do")


@traces_app.command("export")
def traces_export_cmd(
    out: Annotated[Path, typer.Argument(help="JSON lines file to write (must not exist)")],
    days: Annotated[float, typer.Option(help="How far back to look")] = 30,
) -> None:
    """Write the failures for review: candidates for the eval set, nothing in them is verified."""
    with db.connect() as conn:
        try:
            n = trace.export_candidates(conn, timedelta(days=days), out)
        except FileExistsError as e:
            raise typer.BadParameter(str(e)) from e
    typer.echo(f"{n} candidates written to {out}; read each one and remove personal data before use")


@service_app.command("llm-off")
def service_llm_off_cmd() -> None:
    """Kill switch: no model call is made; search still works. Takes effect on the next request."""
    with db.connect() as conn:
        limits.set_llm_enabled(conn, False)
    typer.echo("written answers are OFF")


@service_app.command("llm-on")
def service_llm_on_cmd() -> None:
    """Turn the written answers back on."""
    with db.connect() as conn:
        limits.set_llm_enabled(conn, True)
    typer.echo("written answers are ON")


@service_app.command("status")
def service_status_cmd() -> None:
    """The kill switch and what today's limits have used."""
    settings = limits.Settings()
    with db.connect() as conn:
        enabled = limits.llm_enabled(conn)
        today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        spent, requests = conn.execute(
            "SELECT coalesce(sum(cost_usd), 0)::float, count(*) FROM query_traces WHERE created_at >= %s", (today,)).fetchone()
    typer.echo(f"written answers: {'ON' if enabled else 'OFF'}")
    typer.echo(f"today (UTC): {requests} requests, {spent:.4f} of {settings.cost_per_day_usd:.2f} USD used; "
               f"per client {settings.per_minute} a minute and {settings.per_day} a day")


@cache_app.command("purge")
def cache_purge_cmd() -> None:
    """Delete the expired entries of the answer cache."""
    with db.connect() as conn:
        removed = cache.purge(conn)
        live, _ = cache.counts(conn)
    typer.echo(f"{removed} expired entries deleted, {live} valid ones kept")


@cache_app.command("clear")
def cache_clear_cmd(yes: Annotated[bool, typer.Option("--yes", help="Do not ask for confirmation")] = False) -> None:
    """Delete every entry of the answer cache (asks first): the next questions go to the model again."""
    with db.connect() as conn:
        live, expired = cache.counts(conn)
        typer.echo(f"{live} valid and {expired} expired entries will be deleted.")
        if not yes:
            typer.confirm("Delete them?", abort=True)
        cache.clear(conn)
    typer.echo("deleted")


@cache_app.command("warm")
def cache_warm_cmd(
    file: Annotated[Path, typer.Argument(help="YAML file: a list of example questions")],
    yes: Annotated[bool, typer.Option("--yes", help="Do not ask for confirmation")] = False,
) -> None:
    """Ask the example questions through the real path and store the replies (spends model money; asks first).
    Needs the same settings as `serve`; the service does this by itself at startup when CACHE_WARM_FILE is set."""
    from legalrag.web import build, warm  # the serve and embed extras

    questions = warm.load_questions(file)
    engine, settings = build.production_engine()
    todo = warm.pending(engine, db.connect, settings, questions)
    typer.echo(f"{len(questions)} questions, {len(todo)} not cached yet: about {len(todo) * 0.0004:.4f} USD (0.0004 each, measured on dev answers)")
    if not todo:
        return
    if not yes:
        typer.confirm("Ask them now?", abort=True)
    status = warm.run(engine, db.connect, settings, questions, warm.Status())
    typer.echo(f"asked {status.asked}, stored {status.stored}" + (f", stopped by {status.stopped}" if status.stopped else ""))


@app.command("serve")
def serve_cmd(
    host: Annotated[str, typer.Option(help="Address to listen on; behind a proxy keep the default")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Port to listen on")] = 8000,
) -> None:
    """Start the web service: one process, since bge-m3 is loaded in it (needs the embed and serve extras,
    DEEPSEEK_API_KEY and TRACE_SECRET; CLIENT_IP_HEADER names the header of the proxy that carries the visitor's address)."""
    import uvicorn  # the serve extra

    # access_log off: uvicorn's own access log prints the visitor's raw address, which the privacy notice says is not kept
    uvicorn.run("legalrag.web.build:production_app", factory=True, host=host, port=port, workers=1, proxy_headers=False,
                access_log=False)


@app.command("llm-balance")
def llm_balance_cmd(
    label: Annotated[str, typer.Option(help="Name of this snapshot, e.g. before-pilot")] = "",
) -> None:
    """Read the DeepSeek balance and record it in the ledger (needs DEEPSEEK_API_KEY)."""
    with llm.make_http(os.environ["DEEPSEEK_API_KEY"]) as http:
        balances = llm.balance(http)
    llm.record_balance(llm.LEDGER, balances, label)
    typer.echo(", ".join(f"{amount:.2f} {currency}" for currency, amount in balances.items()))


@app.command("llm-ledger")
def llm_ledger_cmd() -> None:
    """Spend so far, and the last two balance snapshots against the cost estimated between them."""
    calls = [e for e in llm.read_ledger(llm.LEDGER) if e["type"] == "call"]
    typer.echo(f"{len(calls)} calls, {llm.ledger_total(llm.LEDGER):.4f} USD estimated")
    result = llm.reconcile(llm.LEDGER)
    if result is None:
        typer.echo("fewer than two balance snapshots: run llm-balance before and after a run")
        return
    drop = ", ".join(f"{amount:.4f} {currency}" for currency, amount in result["balance_drop"].items())
    typer.echo(f"between the last two snapshots: {result['calls']} calls, "
               f"{result['estimated_usd']:.4f} USD estimated, balance dropped {drop}")

"""Commands on the running service: traces, the kill switch, and the model spend."""

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated

import typer

from legalrag import llm
from legalrag.answering import limits, trace
from legalrag.index import db

app = typer.Typer(no_args_is_help=True)
traces_app = typer.Typer(no_args_is_help=True, help="Look at the traces of the service: failures, summary, purge, export.")
service_app = typer.Typer(no_args_is_help=True, help="Switch the written answers of the running service on or off.")
app.add_typer(traces_app, name="traces")
app.add_typer(service_app, name="service")


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


@traces_app.command("purge")
def traces_purge_cmd(yes: Annotated[bool, typer.Option("--yes", help="Do not ask for confirmation")] = False) -> None:
    """Delete the traces past their 30-day expiry; asks first."""
    with db.connect() as conn:
        n = trace.expired(conn)
        typer.echo(f"{n} expired traces will be deleted.")
        if n and not yes:
            typer.confirm("Delete them?", abort=True)
        if n:
            trace.purge(conn)
    typer.echo("deleted" if n else "nothing to delete")


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

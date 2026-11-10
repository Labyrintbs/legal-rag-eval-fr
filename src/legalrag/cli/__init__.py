"""The `legalrag` command line: the commands by job, one module each."""

import typer

from legalrag.cli import corpus, evaluation, index, service

app = typer.Typer(no_args_is_help=True)
for sub in (corpus.app, index.app, evaluation.app, service.app):
    app.add_typer(sub)

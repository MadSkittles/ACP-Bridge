from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path
from typing import Annotated

import typer

from acp_bridge.config import load_local_config, load_worker_config
from acp_bridge.local_client import LocalClient
from acp_bridge.worker import Worker, run_worker

app = typer.Typer(no_args_is_help=True)
worker_app = typer.Typer(no_args_is_help=True)
app.add_typer(worker_app, name="worker")


def _client(config_path: Path | None = None) -> LocalClient:
    config = load_local_config(config_path)
    return LocalClient(relay_url=config.relay_url, token=config.token)


@app.command()
def devboxes(
    config: Annotated[Path | None, typer.Option("--config", help="Local config file.")] = None,
) -> None:
    """Show the default devbox configured for this client."""
    local_config = load_local_config(config)
    if local_config.default_devbox_id:
        typer.echo(local_config.default_devbox_id)
    else:
        typer.echo("No default devbox configured.")


@app.command()
def ping(
    devbox_id: str,
    config: Annotated[Path | None, typer.Option("--config", help="Local config file.")] = None,
) -> None:
    """Check whether a devbox can be reached through the relay."""
    result = asyncio.run(_client(config).ping(devbox_id))
    typer.echo(json.dumps(result, indent=2))


@app.command()
def run(
    devbox_id: str,
    agent: Annotated[str, typer.Option("--agent", help="Agent profile name.")] = "codex",
    cwd: Annotated[str, typer.Option("--cwd", help="Allowed worker cwd.")] = ".",
    prompt: Annotated[str, typer.Option("--prompt", help="Prompt text to execute.")] = "",
    timeout_sec: Annotated[
        float | None, typer.Option("--timeout-sec", help="Run timeout in seconds.")
    ] = None,
    config: Annotated[Path | None, typer.Option("--config", help="Local config file.")] = None,
) -> None:
    """Run a remote CLI agent task."""

    def print_stream(event) -> None:
        typer.echo(event.data, nl=False, err=(event.stream == "stderr"))

    result = asyncio.run(
        _client(config).run(
            devbox_id,
            agent,
            cwd,
            prompt,
            timeout_sec=timeout_sec,
            stream_callback=print_stream,
        )
    )
    typer.echo(json.dumps(result.model_dump(), indent=2))
    if result.status != "succeeded":
        raise typer.Exit(code=1)


@app.command()
def cancel(
    run_id: str,
    devbox_id: Annotated[
        str | None, typer.Option("--devbox-id", help="Optional devbox hint for routing.")
    ] = None,
    config: Annotated[Path | None, typer.Option("--config", help="Local config file.")] = None,
) -> None:
    """Cancel a remote run."""
    asyncio.run(_client(config).cancel(run_id, devbox_id))
    typer.echo(f"cancel requested: {run_id}")


@worker_app.command("run")
def worker_run(
    config: Annotated[Path | None, typer.Option("--config", help="Worker config file.")] = None,
) -> None:
    """Connect this host as a worker."""
    asyncio.run(run_worker(config))


@worker_app.command("install-task")
def worker_install_task(
    config: Annotated[Path | None, typer.Option("--config", help="Worker config file.")] = None,
    task_name: Annotated[str, typer.Option("--task-name")] = "ACP Bridge Worker",
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
) -> None:
    """Install a Windows Task Scheduler login task for the worker."""
    worker = Worker(load_worker_config(config))
    command = worker.build_install_task_command(
        task_name=task_name,
        config_path=str(config) if config else None,
    )
    if dry_run:
        typer.echo(" ".join(command))
        return
    subprocess.run(command, check=True)


@worker_app.command("uninstall-task")
def worker_uninstall_task(
    config: Annotated[Path | None, typer.Option("--config", help="Worker config file.")] = None,
    task_name: Annotated[str, typer.Option("--task-name")] = "ACP Bridge Worker",
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
) -> None:
    """Remove the Windows Task Scheduler login task for the worker."""
    worker = Worker(load_worker_config(config))
    command = worker.build_uninstall_task_command(task_name=task_name)
    if dry_run:
        typer.echo(" ".join(command))
        return
    subprocess.run(command, check=True)

"""CLI entry point for lgdebug.

Commands:
    lgdebug run           — start the debug server + open the visualizer
    lgdebug server        — start only the API server (headless)
    lgdebug list          — list recorded executions
    lgdebug show <id>     — print execution summary to terminal
    lgdebug clean         — delete all debug data
"""

from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path


def cli(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="lgdebug",
        description="LangGraph State Debugger — Redux DevTools for AI agents",
    )
    subparsers = parser.add_subparsers(dest="command")

    # --- run ---
    run_parser = subparsers.add_parser("run", help="Start debug server and open visualizer")
    run_parser.add_argument("--host", default="127.0.0.1", help="Server host (default: 127.0.0.1)")
    run_parser.add_argument("--port", type=int, default=6274, help="Server port (default: 6274)")
    run_parser.add_argument("--db", default=".lgdebug/debug.db", help="Database path")
    run_parser.add_argument("--no-browser", action="store_true", help="Don't auto-open browser")

    # --- server ---
    server_parser = subparsers.add_parser("server", help="Start API server only")
    server_parser.add_argument("--host", default="127.0.0.1")
    server_parser.add_argument("--port", type=int, default=6274)
    server_parser.add_argument("--db", default=".lgdebug/debug.db")

    # --- list ---
    subparsers.add_parser("list", help="List recorded executions")

    # --- show ---
    show_parser = subparsers.add_parser("show", help="Show execution details")
    show_parser.add_argument("execution_id", help="Execution ID to display")

    # --- clean ---
    clean_parser = subparsers.add_parser("clean", help="Delete all debug data")
    clean_parser.add_argument("--db", default=".lgdebug/debug.db")

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    if args.command == "run":
        _cmd_run(args)
    elif args.command == "server":
        _cmd_server(args)
    elif args.command == "list":
        _cmd_list(args)
    elif args.command == "show":
        _cmd_show(args)
    elif args.command == "clean":
        _cmd_clean(args)


def _cmd_run(args: argparse.Namespace) -> None:
    """Start the debug server and open the browser."""
    import uvicorn

    from lgdebug.core.config import DebugConfig
    from lgdebug.server.app import create_app

    config = DebugConfig(
        db_path=Path(args.db),
        server_host=args.host,
        server_port=args.port,
        auto_open_browser=not args.no_browser,
    )
    app = create_app(config)

    url = f"http://{args.host}:{args.port}"
    print(f"\n  lgdebug server starting at {url}")
    print(f"  API docs: {url}/api/docs")
    print(f"  Database: {args.db}\n")

    if config.auto_open_browser:
        import threading

        def _open_browser() -> None:
            import time
            time.sleep(1.5)  # Wait for server to be ready.
            webbrowser.open(url)

        threading.Thread(target=_open_browser, daemon=True).start()

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


def _cmd_server(args: argparse.Namespace) -> None:
    """Start only the API server."""
    import uvicorn

    from lgdebug.core.config import DebugConfig
    from lgdebug.server.app import create_app

    config = DebugConfig(
        db_path=Path(args.db),
        server_host=args.host,
        server_port=args.port,
        auto_open_browser=False,
    )
    app = create_app(config)

    print(f"\n  lgdebug API server at http://{args.host}:{args.port}")
    print(f"  Database: {args.db}\n")

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


def _cmd_list(args: argparse.Namespace) -> None:
    """List executions from the database."""
    import asyncio

    from lgdebug.storage.sqlite import SQLiteStorage

    db_path = Path(".lgdebug/debug.db")
    if not db_path.exists():
        print("No debug data found. Run your LangGraph app with debugging enabled first.")
        return

    async def _list() -> None:
        storage = SQLiteStorage(db_path)
        await storage.initialize()
        executions = await storage.list_executions()
        await storage.close()

        if not executions:
            print("No executions recorded.")
            return

        print(f"\n{'ID':<20} {'Graph':<20} {'Status':<12} {'Steps':<8} {'Started'}")
        print("-" * 80)
        for ex in executions:
            print(
                f"{ex['execution_id']:<20} "
                f"{ex['graph_name']:<20} "
                f"{ex['status']:<12} "
                f"{ex['step_count']:<8} "
                f"{ex['started_at']}"
            )
        print()

    asyncio.run(_list())


def _cmd_show(args: argparse.Namespace) -> None:
    """Show detailed execution info."""
    import asyncio
    import json

    from lgdebug.storage.sqlite import SQLiteStorage

    db_path = Path(".lgdebug/debug.db")
    if not db_path.exists():
        print("No debug data found.")
        return

    async def _show() -> None:
        storage = SQLiteStorage(db_path)
        await storage.initialize()
        execution = await storage.get_execution(args.execution_id)
        if execution is None:
            print(f"Execution '{args.execution_id}' not found.")
            await storage.close()
            return

        steps = await storage.list_steps(args.execution_id)
        await storage.close()

        print(f"\nExecution: {execution.execution_id}")
        print(f"Graph:     {execution.graph_name}")
        print(f"Status:    {execution.status.value}")
        print(f"Steps:     {execution.step_count}")
        print(f"Started:   {execution.started_at.isoformat()}")
        if execution.ended_at:
            print(f"Ended:     {execution.ended_at.isoformat()}")

        print(f"\nTimeline:")
        for step in steps:
            status_icon = {
                "completed": "+",
                "failed": "X",
                "running": "~",
            }.get(step["status"], "?")
            diff = step["state_diff"]
            changes = len(diff.get("changed", [])) + len(diff.get("added", [])) + len(diff.get("removed", []))
            print(f"  [{status_icon}] {step['step_index']:>3}. {step['node_name']:<25} ({changes} changes)")

        print()

    asyncio.run(_show())


def _cmd_clean(args: argparse.Namespace) -> None:
    """Delete the debug database."""
    db_path = Path(args.db)
    if db_path.exists():
        db_path.unlink()
        print(f"Deleted {db_path}")
        # Also clean WAL/SHM files.
        for suffix in ["-wal", "-shm"]:
            p = db_path.with_name(db_path.name + suffix)
            if p.exists():
                p.unlink()
    else:
        print("No debug data to clean.")


if __name__ == "__main__":
    cli()

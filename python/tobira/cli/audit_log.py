"""tobira audit-log - Search and display audit log events."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any


def register(subparsers: "argparse._SubParsersAction[Any]") -> None:
    """Register the ``audit-log`` subcommand.

    Args:
        subparsers: The subparsers action from the top-level parser.
    """
    parser = subparsers.add_parser(
        "audit-log",
        help="Search and display audit log events",
        description=(
            "Read audit events from the configured audit log store. "
            "By default shows the 20 most recent events."
        ),
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to tobira.toml configuration file",
    )
    parser.add_argument(
        "--last",
        type=int,
        default=20,
        help="Number of most recent events to show (default: 20)",
    )
    parser.add_argument(
        "--json",
        dest="output_json",
        action="store_true",
        help="Output events as JSON array",
    )
    parser.add_argument(
        "--user",
        help="Filter events by user name",
    )
    parser.add_argument(
        "--action",
        help="Filter events by action type",
    )
    parser.add_argument(
        "--status",
        choices=["allowed", "denied", "error"],
        help="Filter events by status",
    )
    parser.set_defaults(func=_run)


def _run(args: argparse.Namespace) -> int:
    """Execute the audit-log command.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code (0 for success, non-zero for failure).
    """
    from tobira.config import load_toml
    from tobira.errors import format_cli_error
    from tobira.serving.audit import create_audit_logger, load_audit_config

    config = load_toml(args.config)
    audit_section = config.get("audit")
    audit_cfg = load_audit_config(audit_section)

    if not audit_cfg.enabled:
        print(
            format_cli_error(
                "CONFIG_MISSING_SECTION",
                "Audit logging is not enabled in the configuration.",
                "Add [audit] section with enabled = true to tobira.toml",
            ),
            file=sys.stderr,
        )
        return 1

    audit_logger = create_audit_logger(audit_cfg)
    if audit_logger is None:
        print("Error: Failed to create audit logger.", file=sys.stderr)
        return 1

    events = audit_logger.read_events(last_n=args.last)

    # Apply filters
    if args.user:
        events = [e for e in events if e.get("user") == args.user]
    if args.action:
        events = [e for e in events if e.get("action") == args.action]
    if args.status:
        events = [e for e in events if e.get("status") == args.status]

    if args.output_json:
        print(json.dumps(events, ensure_ascii=False, indent=2))
    else:
        if not events:
            print("No audit events found.")
            return 0
        for event in events:
            ts = event.get("timestamp", "")
            user = event.get("user", "anonymous")
            role = event.get("role", "none")
            action = event.get("action", "")
            resource = event.get("resource", "")
            status = event.get("status", "")
            detail = event.get("detail", "")
            ip_addr = event.get("ip_address", "")
            latency = event.get("latency_ms")

            status_marker = "+" if status == "allowed" else "-"
            latency_str = f" {latency:.0f}ms" if latency is not None else ""
            detail_str = f" ({detail})" if detail else ""

            print(
                f"[{ts}] {status_marker} {user}({role}) "
                f"{action} {resource} [{ip_addr}]{latency_str}{detail_str}"
            )

    return 0

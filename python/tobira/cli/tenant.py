"""CLI subcommand: ``tobira tenant`` — manage tenants."""

from __future__ import annotations

import argparse
import sys
from typing import Any

from tobira.config import load_toml
from tobira.errors import format_cli_error
from tobira.serving.tenant import (
    load_tenant_configs,
    validate_tenant_id,
)


def register(subparsers: Any) -> None:
    """Register the ``tenant`` subcommand."""
    tenant_parser = subparsers.add_parser(
        "tenant",
        help="Manage tenants",
        description="List, create, or delete tenants defined in tobira.toml.",
    )
    tenant_sub = tenant_parser.add_subparsers(dest="tenant_action")

    # tobira tenant list
    list_parser = tenant_sub.add_parser("list", help="List configured tenants")
    list_parser.add_argument(
        "-c", "--config", required=True, help="Path to tobira.toml"
    )
    list_parser.set_defaults(func=_cmd_tenant_list)

    # tobira tenant create
    create_parser = tenant_sub.add_parser("create", help="Add a new tenant")
    create_parser.add_argument(
        "-c", "--config", required=True, help="Path to tobira.toml"
    )
    create_parser.add_argument(
        "--name", required=True, help="Tenant identifier"
    )
    create_parser.add_argument(
        "--display-name", default="", help="Human-readable name"
    )
    create_parser.add_argument(
        "--backend-type", default="fasttext", help="Backend type (default: fasttext)"
    )
    create_parser.add_argument(
        "--model-path", default="", help="Path to the model file"
    )
    create_parser.set_defaults(func=_cmd_tenant_create)

    # tobira tenant delete
    delete_parser = tenant_sub.add_parser("delete", help="Remove a tenant")
    delete_parser.add_argument(
        "-c", "--config", required=True, help="Path to tobira.toml"
    )
    delete_parser.add_argument(
        "--name", required=True, help="Tenant identifier to remove"
    )
    delete_parser.set_defaults(func=_cmd_tenant_delete)

    tenant_parser.set_defaults(func=_cmd_tenant_help, _parser=tenant_parser)


def _cmd_tenant_help(args: argparse.Namespace) -> int:
    parser = getattr(args, "_parser", None)
    if parser:
        parser.print_help()
    return 1


def _cmd_tenant_list(args: argparse.Namespace) -> int:
    """Handle ``tobira tenant list``."""
    try:
        config = load_toml(args.config)
    except FileNotFoundError as exc:
        print(format_cli_error("CONFIG_NOT_FOUND", str(exc)), file=sys.stderr)
        return 1

    configs = load_tenant_configs(config)
    if not configs:
        tenants_section = config.get("tenants", {})
        if not tenants_section.get("enabled"):
            print("Multi-tenancy is not enabled. Set [tenants] enabled = true.")
        else:
            print("No tenants configured.")
        return 0

    print(f"Tenants ({len(configs)}):")
    for tc in sorted(configs, key=lambda t: t.tenant_id):
        name_part = f" ({tc.display_name})" if tc.display_name else ""
        backend_type = tc.backend_config.get("type", "?")
        print(f"  {tc.tenant_id}{name_part} — backend: {backend_type}")
    return 0


def _cmd_tenant_create(args: argparse.Namespace) -> int:
    """Handle ``tobira tenant create``."""
    if not validate_tenant_id(args.name):
        print(
            format_cli_error(
                "TENANT_INVALID_ID",
                f"Invalid tenant ID: {args.name!r}",
                hint="Must match [a-zA-Z0-9][a-zA-Z0-9_-]{0,62}.",
            ),
            file=sys.stderr,
        )
        return 1

    try:
        config = load_toml(args.config)
    except FileNotFoundError as exc:
        print(format_cli_error("CONFIG_NOT_FOUND", str(exc)), file=sys.stderr)
        return 1

    existing = load_tenant_configs(config)
    for tc in existing:
        if tc.tenant_id == args.name:
            print(
                format_cli_error(
                    "TENANT_ALREADY_EXISTS",
                    f"Tenant {args.name!r} already exists.",
                ),
                file=sys.stderr,
            )
            return 1

    # Build the TOML snippet to append
    snippet_lines = [
        "",
        f"[tenants.{args.name}]",
    ]
    if args.display_name:
        snippet_lines.append(f'display_name = "{args.display_name}"')
    snippet_lines.append(f"[tenants.{args.name}.backend]")
    snippet_lines.append(f'type = "{args.backend_type}"')
    if args.model_path:
        snippet_lines.append(f'model_path = "{args.model_path}"')
    snippet = "\n".join(snippet_lines) + "\n"

    # Ensure [tenants] enabled = true exists
    tenants_section = config.get("tenants", {})
    if not tenants_section.get("enabled"):
        # Prepend the enabled flag
        snippet = "\n[tenants]\nenabled = true\n" + snippet

    with open(args.config, "a", encoding="utf-8") as f:
        f.write(snippet)

    print(f"Tenant {args.name!r} added to {args.config}")
    return 0


def _cmd_tenant_delete(args: argparse.Namespace) -> int:
    """Handle ``tobira tenant delete``.

    Reads the TOML, removes the tenant section, and rewrites the file.
    """
    if not validate_tenant_id(args.name):
        print(
            format_cli_error(
                "TENANT_INVALID_ID",
                f"Invalid tenant ID: {args.name!r}",
            ),
            file=sys.stderr,
        )
        return 1

    try:
        config = load_toml(args.config)
    except FileNotFoundError as exc:
        print(format_cli_error("CONFIG_NOT_FOUND", str(exc)), file=sys.stderr)
        return 1

    tenants_section = config.get("tenants", {})
    if args.name not in tenants_section:
        print(
            format_cli_error(
                "TENANT_NOT_FOUND",
                f"Tenant {args.name!r} not found in config.",
            ),
            file=sys.stderr,
        )
        return 1

    # Remove the tenant from the parsed config and rewrite
    # We work on the raw file lines to preserve formatting
    import re

    with open(args.config, encoding="utf-8") as f:
        lines = f.readlines()

    # Find and remove the [tenants.<name>] section and its subsections
    pattern = re.compile(
        rf"^\[tenants\.{re.escape(args.name)}(?:\..*)?\]\s*$"
    )
    section_pattern = re.compile(r"^\[.*\]\s*$")

    new_lines: list[str] = []
    skip = False
    for line in lines:
        if pattern.match(line):
            skip = True
            continue
        if skip and section_pattern.match(line) and not pattern.match(line):
            skip = False
        if not skip:
            new_lines.append(line)

    with open(args.config, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    print(f"Tenant {args.name!r} removed from {args.config}")
    return 0

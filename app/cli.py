"""Small operator CLI.

    python -m app.cli hash-password
    python -m app.cli create-client acme --admin
    python -m app.cli health
    python -m app.cli expire
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys

from app.core.audit import CLIENT_CREATED, record
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.security import generate_api_key, hash_password
from app.database.enums import Classification
from app.database.models import Client
from app.database.session import create_all, get_engine, session_scope


def cmd_hash_password(_args) -> int:
    password = getpass.getpass("New admin password: ")
    if len(password) < 12:
        print("refused: use at least 12 characters", file=sys.stderr)
        return 2
    if password != getpass.getpass("Repeat: "):
        print("refused: the two entries did not match", file=sys.stderr)
        return 2
    print("\nADMIN_PASSWORD_HASH=" + hash_password(password))
    return 0


def cmd_create_client(args) -> int:
    create_all(get_engine())
    with session_scope() as session:
        if session.get(Client, args.client_id) is not None:
            print(f"client '{args.client_id}' already exists", file=sys.stderr)
            return 2
        key = generate_api_key()
        session.add(
            Client(
                client_id=args.client_id,
                name=args.name or args.client_id,
                api_key_id=key.key_id,
                api_key_hash=key.hashed,
                is_admin=args.admin,
                may_escalate=args.may_escalate,
                default_classification=Classification(args.default_classification.upper()).value,
                max_external_classification=Classification(args.max_external.upper()).value,
                daily_budget_usd=args.daily_budget,
            )
        )
        record(
            session,
            actor="cli",
            actor_type="operator",
            action=CLIENT_CREATED,
            resource_type="client",
            resource_id=args.client_id,
            detail={"is_admin": args.admin},
        )
    print(json.dumps({"client_id": args.client_id, "api_key": key.plaintext}, indent=2))
    print("\nThis key is shown once and is stored only as a digest. Save it now.", file=sys.stderr)
    return 0


def cmd_health(_args) -> int:
    from app.runtime import Runtime

    runtime = Runtime(get_settings())
    print(json.dumps(runtime.describe(), indent=2))
    runtime.close()
    return 0


def cmd_expire(_args) -> int:
    """Age out memory items and solutions whose time-to-live has elapsed."""
    from app.learning.solution_store import SolutionStore
    from app.memory.long_term import LongTermMemory

    create_all(get_engine())
    with session_scope() as session:
        solutions = SolutionStore(session, "*").expire_due(all_clients=True)
        memories = LongTermMemory(session, "*").expire_due()
    print(json.dumps({"solutions_expired": len(solutions), "memory_expired": memories}, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    # Without this, structlog's default configuration writes to stdout and
    # interleaves log lines with the JSON these commands emit.
    configure_logging(get_settings().LOG_LEVEL, get_settings().LOG_FORMAT)
    parser = argparse.ArgumentParser(prog="ai-helper", description="AI Helper operator CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("hash-password", help="generate an ADMIN_PASSWORD_HASH").set_defaults(
        func=cmd_hash_password
    )

    create = sub.add_parser("create-client", help="create a client and issue its API key")
    create.add_argument("client_id")
    create.add_argument("--name")
    create.add_argument("--admin", action="store_true")
    create.add_argument("--may-escalate", action="store_true", default=False)
    create.add_argument("--default-classification", default="INTERNAL")
    create.add_argument("--max-external", default="INTERNAL")
    create.add_argument("--daily-budget", type=float, default=None)
    create.set_defaults(func=cmd_create_client)

    sub.add_parser("health", help="print component status").set_defaults(func=cmd_health)
    sub.add_parser("expire", help="expire memory and solutions past their TTL").set_defaults(
        func=cmd_expire
    )

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

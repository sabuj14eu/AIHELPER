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


# Pairs used to measure an embedder's score distribution. Each "related" pair
# is a question and a paraphrase of it that a working retrieval layer must
# match; each "unrelated" pair must not match. Deliberately plain and
# domain-neutral — this measures the embedder, not the deployment's content.
CALIBRATION_RELATED = [
    ("What is the VAT rate in Poland?", "what's the Polish VAT rate"),
    ("How are invoices numbered?", "what is the invoice numbering scheme"),
    ("When is the contribution due?", "what is the deadline for paying the contribution"),
    ("Explain the look-back rule and when it applies.",
     "When does the look-back rule apply, and what exactly does it say?"),
    ("Who is allowed to approve an expense?", "which people can sign off on expenses"),
]
CALIBRATION_UNRELATED = [
    ("What is the VAT rate in Poland?", "How do I bake sourdough bread at home?"),
    ("How are invoices numbered?", "Chess openings are classified by ECO code."),
    ("When is the contribution due?", "The train to Krakow leaves from platform four."),
    ("Explain the look-back rule and when it applies.", "Photosynthesis converts light to energy."),
    ("Who is allowed to approve an expense?", "The capital of France is Paris."),
]


def cmd_calibrate(args) -> int:
    """Measure the ACTIVE embedder and check the configured thresholds fit it.

    Why this exists: the thresholds are chosen from which *class* of embedder
    is running (semantic or lexical), never from a measurement of the model
    actually installed. If a deployment's embedding model scores on a different
    scale than the defaults assume, solution reuse silently stops working and
    every paraphrase re-escalates and pays. That failure is invisible without
    a measurement, so here is the measurement.
    """
    from app.memory.embeddings import cosine
    from app.memory.thresholds import for_embedder
    from app.runtime import Runtime

    settings = get_settings()
    runtime = Runtime(settings)
    embedder = runtime.embedder
    thresholds = for_embedder(embedder, settings)

    def scores(pairs):
        out = []
        for first, second in pairs:
            a, b = embedder.embed([first, second])
            out.append(cosine(a, b))
        return sorted(out)

    try:
        related = scores(CALIBRATION_RELATED)
        unrelated = scores(CALIBRATION_UNRELATED)
    except Exception as exc:
        print(f"could not embed: {type(exc).__name__}: {exc}", file=sys.stderr)
        runtime.close()
        return 1
    finally:
        pass

    worst_related = min(related)
    best_unrelated = max(unrelated)
    memory_ok = best_unrelated < thresholds.memory < worst_related
    reuse_ok = thresholds.solution_reuse <= worst_related

    # Decide the verdict BEFORE printing, so the JSON a machine consumes
    # actually carries it.
    if worst_related <= best_unrelated:
        verdict = "no_separation"
    elif not memory_ok or not reuse_ok:
        verdict = "thresholds_misplaced"
    else:
        verdict = "ok"

    report = {
        "embedder": embedder.id,
        "semantic": embedder.semantic,
        "dimensions": embedder.dim,
        "related_pairs": [round(s, 4) for s in related],
        "unrelated_pairs": [round(s, 4) for s in unrelated],
        "worst_related": round(worst_related, 4),
        "best_unrelated": round(best_unrelated, 4),
        "thresholds": thresholds.as_dict(),
        "memory_threshold_fits": memory_ok,
        "reuse_threshold_fits": reuse_ok,
        "verdict": verdict,
    }
    print(json.dumps(report, indent=2))

    names = (
        "MEMORY_SIMILARITY_THRESHOLD / SOLUTION_REUSE_THRESHOLD"
        if embedder.semantic
        else "LEXICAL_MEMORY_SIMILARITY_THRESHOLD / LEXICAL_SOLUTION_REUSE_THRESHOLD"
    )
    measurement = (
        f"  Paraphrases of the same question score as low as {worst_related:.3f}.\n"
        f"  Unrelated text scores as high as {best_unrelated:.3f}.\n"
    )
    consequence = (
        "\nLeft as is, learned solutions will not be reused for a reworded\n"
        "question, and every paraphrase will escalate to a paid provider.\n"
    )

    if verdict == "no_separation":
        # No threshold can separate the two populations. Saying "adjust the
        # threshold" here would be wrong advice: there is nothing to adjust it
        # to. The embedder itself is the problem.
        print(
            "\nTHIS EMBEDDER CANNOT SEPARATE RELATED FROM UNRELATED TEXT.\n"
            + measurement
            + "  Those ranges overlap, so no threshold exists that admits the\n"
            "  first and rejects the second. This is not a tuning problem.\n"
            + consequence
            + "\nInstall a real embedding model and re-run:\n"
            "  ollama pull nomic-embed-text\n"
            "  python -m app.cli calibrate",
            file=sys.stderr,
        )
        runtime.close()
        return 1

    if verdict == "thresholds_misplaced":
        print(
            "\nTHE THRESHOLDS DO NOT FIT THIS EMBEDDER.\n"
            + measurement
            + f"  A retrieval threshold must sit strictly between those; it is "
            f"{thresholds.memory:.3f}.\n"
            f"  A reuse threshold must be at or below {worst_related:.3f}; it is "
            f"{thresholds.solution_reuse:.3f}.\n"
            + consequence
            + f"\nSet {names} to values inside the measured gap\n"
            f"(for example {(best_unrelated + worst_related) / 2:.2f} and "
            f"{max(best_unrelated + 0.01, worst_related - 0.05):.2f}) and re-run this command.",
            file=sys.stderr,
        )
        runtime.close()
        return 1

    print(
        f"\nThresholds fit the measured distribution "
        f"(gap {best_unrelated:.3f} … {worst_related:.3f}).",
        file=sys.stderr,
    )
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
    sub.add_parser(
        "calibrate",
        help="measure the active embedder and check the similarity thresholds fit it",
    ).set_defaults(func=cmd_calibrate)
    sub.add_parser("expire", help="expire memory and solutions past their TTL").set_defaults(
        func=cmd_expire
    )

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

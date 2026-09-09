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
# The same question with ONE answer-changing detail swapped. A reuse gate that
# admits one of these serves a confident wrong answer, for free. Measured on a
# real embedding model (nomic-embed-text, 40 pairs, audit/measure_embedder.py)
# these score in the SAME range as paraphrases: no cosine threshold separates
# them, and lowering the reuse threshold admits more of them for almost no
# paraphrase gained. They are measured here so that admission is printed on
# every run rather than discovered in production.
CALIBRATION_HARD_NEGATIVE = [
    ("What is the VAT rate in Poland?", "What is the VAT rate in Germany?"),
    ("What is the deadline for the monthly VAT return?",
     "What is the deadline for the quarterly VAT return?"),
    ("What is the minimum wage in 2025?", "What is the minimum wage in 2026?"),
    ("What happens if I pay ZUS late?", "What happens if I pay ZUS early?"),
    ("Which port does the API listen on?", "Which port does the database listen on?"),
    ("Can I deduct a laptop bought for the business?", "Can I deduct a car bought for the business?"),
    ("What is the daily budget for API calls?", "What is the monthly budget for API calls?"),
    ("How many days are in February 2024?", "How many days are in February 2023?"),
    ("Is VAT registration mandatory above the turnover limit?",
     "Is VAT registration mandatory below the turnover limit?"),
    ("What is the maximum request size?", "What is the minimum request size?"),
]


def cmd_calibrate(args) -> int:
    """Measure the ACTIVE embedder and check the configured thresholds fit it.

    Why this exists: the thresholds are chosen from which *class* of embedder
    is running (semantic or lexical), never from a measurement of the model
    actually installed. If a deployment's embedding model scores on a different
    scale than the defaults assume, retrieval silently stops finding
    paraphrases and every reworded question re-escalates and pays. That failure
    is invisible without a measurement, so here is the measurement.

    What it refuses, and what it deliberately does not:

    * It refuses an embedder that cannot separate related from unrelated text
      at all, and a retrieval threshold that sits outside the measured gap.
    * It refuses a reuse threshold looser than the retrieval threshold: a
      learned solution is offered as THE answer, memory only as evidence.
    * It does NOT demand that every paraphrase clears the reuse threshold.
      Measured on a real embedder, the only way to satisfy that was to lower
      the threshold into the range where one-detail variants of a learned
      question score, trading a confident wrong answer for each paraphrase
      gained. Instead it measures and prints how many such variants the
      reuse gate admits, so nobody lowers the bar to buy recall.
    """
    from app.learning.similarity import jaccard
    from app.memory.embeddings import cosine
    from app.memory.retrieval import LEXICAL_WITNESS
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
            out.append((cosine(a, b), jaccard(first, second)))
        return out

    try:
        related = scores(CALIBRATION_RELATED)
        unrelated = scores(CALIBRATION_UNRELATED)
        hard = scores(CALIBRATION_HARD_NEGATIVE)
    except Exception as exc:
        print(f"could not embed: {type(exc).__name__}: {exc}", file=sys.stderr)
        runtime.close()
        return 1

    related_cos = sorted(c for c, _ in related)
    unrelated_cos = sorted(c for c, _ in unrelated)
    hard_cos = sorted(c for c, _ in hard)
    worst_related = min(related_cos)
    best_unrelated = max(unrelated_cos)
    memory_ok = best_unrelated < thresholds.memory < worst_related
    reuse_ok = thresholds.solution_reuse >= thresholds.memory

    def clears_reuse(cos_value: float, lexical: float) -> bool:
        # Both witnesses, exactly as app/memory/retrieval.py applies them.
        return cos_value >= thresholds.solution_reuse and lexical >= LEXICAL_WITNESS

    paraphrases_reusable = sum(1 for c, lex in related if clears_reuse(c, lex))
    hard_admitted = sum(1 for c, lex in hard if clears_reuse(c, lex))

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
        "related_pairs": [round(s, 4) for s in related_cos],
        "unrelated_pairs": [round(s, 4) for s in unrelated_cos],
        "hard_negative_pairs": [round(s, 4) for s in hard_cos],
        "worst_related": round(worst_related, 4),
        "best_unrelated": round(best_unrelated, 4),
        "thresholds": thresholds.as_dict(),
        "reuse_gate": {
            "threshold": thresholds.solution_reuse,
            "lexical_witness": LEXICAL_WITNESS,
            "paraphrases_reusable": f"{paraphrases_reusable}/{len(related)}",
            "hard_negatives_admitted": f"{hard_admitted}/{len(hard)}",
        },
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
    hard_note = (
        f"\nNOTE: {hard_admitted} of {len(hard)} one-detail variants of a learned question clear\n"
        f"the reuse gate at {thresholds.solution_reuse:.2f} (cosine, plus the lexical witness).\n"
        "No cosine threshold separates such a variant from a paraphrase on this\n"
        "embedder, and lowering the reuse threshold admits MORE of them — do NOT\n"
        "lower SOLUTION_REUSE_THRESHOLD to gain paraphrase recall. For these the\n"
        "local model's context discipline is the guard; measure it with\n"
        "audit/measure_reuse_discipline.py.\n"
        if hard_admitted
        else ""
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
            "\nLeft as is, learned solutions will not be reused for a reworded\n"
            "question, and every paraphrase will escalate to a paid provider.\n"
            "\nInstall a real embedding model and re-run:\n"
            "  ollama pull nomic-embed-text\n"
            "  python -m app.cli calibrate",
            file=sys.stderr,
        )
        runtime.close()
        return 1

    if verdict == "thresholds_misplaced":
        problems = ""
        if not memory_ok:
            problems += (
                f"  A retrieval threshold must sit strictly between those; it is "
                f"{thresholds.memory:.3f}.\n"
            )
        if not reuse_ok:
            problems += (
                f"  A reuse threshold must be at or above the retrieval threshold "
                f"({thresholds.memory:.3f}); it is {thresholds.solution_reuse:.3f}.\n"
            )
        suggested_memory = (
            (best_unrelated + worst_related) / 2 if not memory_ok else thresholds.memory
        )
        print(
            "\nTHE THRESHOLDS DO NOT FIT THIS EMBEDDER.\n"
            + measurement
            + problems
            + "\nLeft as is, retrieval either misses paraphrases (and every reworded\n"
            "question escalates and pays) or admits noise, and a reuse gate looser\n"
            "than retrieval serves answers it would not even have offered as evidence.\n"
            f"\nSet {names} so that the first lies inside the measured gap\n"
            f"(for example {suggested_memory:.2f}) and the second is at or above it\n"
            f"(for example {max(suggested_memory, thresholds.solution_reuse):.2f}), then re-run.\n"
            "Never lower the reuse threshold to admit more paraphrases: the same\n"
            "range admits one-detail variants of a learned question, which are\n"
            "confident wrong answers."
            + hard_note,
            file=sys.stderr,
        )
        runtime.close()
        return 1

    print(
        f"\nThresholds fit the measured distribution "
        f"(gap {best_unrelated:.3f} … {worst_related:.3f})." + hard_note,
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

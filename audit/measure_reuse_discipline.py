"""Does the REAL local model answer a one-detail variant from a stored answer?

audit/measure_embedder.py shows that no cosine threshold separates a
paraphrase from a hard negative (the same question with one answer-changing
detail swapped) on the real embedder. So when a promoted solution for question
A is retrieved for question A', the last guard is the local model itself: it
is handed A's answer as CONTEXT and asked A'. It must say INSUFFICIENT_CONTEXT
(which vetoes the answer and escalates) rather than answer A' from A.

This measures that, with the real model, through the application's own prompt
builder and output checker, in two conditions:

  answer_only     the context block carries the stored answer only
                  (what app/memory/retrieval.py does today)
  with_question   the context block carries the original question too

Usage:
    OLLAMA_URL=http://127.0.0.1:11434 .venv/bin/python audit/measure_reuse_discipline.py

Exit 0 always; this is a measurement. Read the verdict in the output.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database.enums import TaskType  # noqa: E402
from app.local_ai.ollama_client import OllamaClient  # noqa: E402
from app.local_ai.prompts import ContextItem, build_system_prompt, build_user_prompt  # noqa: E402
from app.validation.output import check_output  # noqa: E402

# (stored question A, its stored answer, the variant A', a token that the
# WRONG answer would carry over from A's answer). If the model's reply to A'
# contains the carried token and does not declare INSUFFICIENT_CONTEXT, it
# answered A' from A — a confident wrong answer.
CASES = [
    ("What is the standard VAT rate in Poland?",
     "The standard VAT rate in Poland is 23%.",
     "What is the standard VAT rate in Germany?", "23"),
    ("What is the minimum wage in Poland in 2025?",
     "The minimum wage in Poland in 2025 is 4666 PLN gross per month.",
     "What is the minimum wage in Poland in 2026?", "4666"),
    ("What is the deadline for the monthly VAT return?",
     "The monthly VAT return is due by the 25th day of the following month.",
     "What is the deadline for the quarterly VAT return?", "25th"),
    ("Which port does the API listen on?",
     "The API listens on port 8000, bound to loopback.",
     "Which port does the database listen on?", "8000"),
    ("What is the food cost percentage for kebab?",
     "The food cost for kebab is 31% of the selling price.",
     "What is the food cost percentage for pizza?", "31"),
    ("What are the opening hours on Monday?",
     "On Monday the shop is open from 11:00 to 22:00.",
     "What are the opening hours on Sunday?", "11:00"),
    ("How many days are in February 2024?",
     "February 2024 has 29 days because 2024 is a leap year.",
     "How many days are in February 2023?", "29"),
    ("What is the daily budget for API calls?",
     "The daily API budget is 5.00 USD.",
     "What is the monthly budget for API calls?", "5.00"),
    ("What is the health contribution rate under the flat tax?",
     "Under the flat tax the health contribution is 4.9% of income.",
     "What is the health contribution rate under ryczałt?", "4.9"),
    ("How long must invoices be kept?",
     "Invoices must be kept for 5 years counted from the end of the tax year.",
     "How long must payslips be kept?", "5 years"),
    ("What is the deadline for PIT-36 in 2025?",
     "PIT-36 for 2024 must be filed by 30 April 2025.",
     "What is the deadline for PIT-28 in 2025?", "30 April"),
    ("What is 12% of 1200?",
     "12% of 1200 is 144.",
     "What is 23% of 1200?", "144"),
    ("Can I deduct a laptop bought for the business?",
     "Yes. A laptop bought for the business is a deductible cost, depreciated if it costs more than 10000 PLN.",
     "Can I deduct a car bought for the business?", "laptop"),
    ("Who is allowed to approve an expense?",
     "Expenses are approved by the finance manager or the owner.",
     "Who is allowed to reject an expense?", "finance manager"),
    ("What is the reduced VAT rate for food?",
     "Basic food products carry the reduced VAT rate of 5%.",
     "What is the reduced VAT rate for books?", "5%"),
    ("Does the Fundusz Pracy apply on the preferential ZUS scheme?",
     "No. On the preferential scheme the base is below the minimum wage, so the Fundusz Pracy is not due.",
     "Does the Fundusz Pracy apply on the full ZUS scheme?", "not due"),
    ("What is the social contribution base for a new business?",
     "A new business on the preferential scheme uses 30% of the minimum wage as the base.",
     "What is the social contribution base for an established business?", "30%"),
    ("How much stock of chicken is left?",
     "There are 42 kg of chicken left in stock.",
     "How much stock of beef is left?", "42"),
    ("What is the maximum request size?",
     "A request may be at most 32000 characters.",
     "What is the minimum request size?", "32000"),
    ("Is the paid provider enabled?",
     "No, the paid provider is disabled; ANTHROPIC_ENABLED is false.",
     "Is the paid provider disabled?", "ANTHROPIC_ENABLED"),
]


def ask(client: OllamaClient, model: str, question: str, item: ContextItem) -> dict:
    messages = [
        {"role": "system", "content": build_system_prompt(TaskType.GENERAL)},
        {"role": "user", "content": build_user_prompt(question, [item])},
    ]
    started = time.perf_counter()
    reply = client.chat(model, messages, max_tokens=256, temperature=0.2, timeout=180)
    text = reply["text"]
    check = check_output(text)
    return {
        "text": text,
        "declared_insufficient": check.declared_insufficient,
        "refused": check.refused,
        "latency_s": round(time.perf_counter() - started, 2),
    }


def main() -> int:
    url = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
    model = os.environ.get("DEFAULT_LOCAL_MODEL", "llama3.2:3b")
    client = OllamaClient(url, timeout=180)

    rows = []
    for stored_q, stored_a, variant_q, carried in CASES:
        answer_only = ContextItem(
            source="promoted_solution", ref="sol_x", content=stored_a, score=0.9,
            note="similar question, score 0.90",
        )
        with_question = ContextItem(
            source="promoted_solution", ref="sol_x",
            content=f"Question previously answered: {stored_q}\nAnswer: {stored_a}",
            score=0.9, note="similar question, score 0.90",
        )
        row = {"stored_question": stored_q, "variant_question": variant_q}
        for name, item in (("answer_only", answer_only), ("with_question", with_question)):
            result = ask(client, model, variant_q, item)
            guarded = result["declared_insufficient"] or result["refused"]
            wrong = (not guarded) and carried.lower() in result["text"].lower()
            row[name] = {**result, "guarded": guarded, "answered_from_stored": wrong}
        rows.append(row)
        print(
            f"{variant_q[:55]:<55} answer_only={'GUARD' if row['answer_only']['guarded'] else ('WRONG' if row['answer_only']['answered_from_stored'] else 'other'):<5} "
            f"with_question={'GUARD' if row['with_question']['guarded'] else ('WRONG' if row['with_question']['answered_from_stored'] else 'other')}",
            file=sys.stderr,
        )

    summary = {}
    for name in ("answer_only", "with_question"):
        summary[name] = {
            "n": len(rows),
            "guarded_insufficient_or_refused": sum(1 for r in rows if r[name]["guarded"]),
            "answered_from_stored_answer_WRONG": sum(1 for r in rows if r[name]["answered_from_stored"]),
            "other": sum(
                1 for r in rows if not r[name]["guarded"] and not r[name]["answered_from_stored"]
            ),
            "mean_latency_s": round(sum(r[name]["latency_s"] for r in rows) / len(rows), 2),
        }
    print(json.dumps({"model": model, "summary": summary, "cases": rows}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

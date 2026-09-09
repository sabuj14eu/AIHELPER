"""Measure the ACTIVE embedder against a larger, harder pair set than `calibrate`.

`python -m app.cli calibrate` uses five paraphrase pairs and five unrelated
pairs. That is enough to detect an embedder that cannot separate anything,
and it is nowhere near enough to place a reuse threshold — n<20 is luck.

This script measures three populations with the real embedding model, using
the application's own cosine and lexical (jaccard) functions so the numbers
are the ones the retrieval layer would actually see:

  related        a question and a paraphrase of it — MUST be reused
  unrelated      a question and text about something else — must not match
  hard negative  the same question with ONE answer-changing detail swapped
                 (country, year, entity, sign, direction, quantity) — must
                 NOT be reused; a reused answer here is a confident wrong answer

For the solution-reuse gate it then reports, at several candidate thresholds,
how many paraphrases would be reused (recall) and how many hard negatives
would be wrongly reused (false reuse), applying BOTH witnesses the retrieval
layer applies: cosine >= threshold AND jaccard >= 0.25.

Usage:
    OLLAMA_URL=http://127.0.0.1:11434 .venv/bin/python audit/measure_embedder.py

Exit 0 always; this is a measurement, not a gate. The verdict is in the output.
"""

from __future__ import annotations

import json
import os
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.learning.similarity import jaccard  # noqa: E402
from app.local_ai.ollama_client import OllamaClient  # noqa: E402
from app.memory.embeddings import OllamaEmbedder, cosine  # noqa: E402

RELATED = [
    ("What is the VAT rate in Poland?", "what's the Polish VAT rate"),
    ("How are invoices numbered?", "what is the invoice numbering scheme"),
    ("When is the contribution due?", "what is the deadline for paying the contribution"),
    ("Explain the look-back rule and when it applies.",
     "When does the look-back rule apply, and what exactly does it say?"),
    ("Who is allowed to approve an expense?", "which people can sign off on expenses"),
    ("How do I reset my password?", "I forgot my password, how can I change it?"),
    ("What is the deadline for filing the monthly VAT return?",
     "By when must the monthly VAT return be submitted?"),
    ("Can I deduct a laptop bought for the business?",
     "Is a laptop purchased for company use tax deductible?"),
    ("How long should invoices be kept?", "For how many years must I store invoices?"),
    ("What happens if I pay ZUS late?", "What are the consequences of a late ZUS payment?"),
    ("How do I add a new user to the system?", "What are the steps to create a user account?"),
    ("Why is the server returning a 502 error?", "What causes the 502 bad gateway response?"),
    ("How do I back up the database?", "What is the procedure for making a database backup?"),
    ("Which port does the API listen on?", "What port is the API served from?"),
    ("How is the health contribution calculated under the flat tax?",
     "Under the flat tax, how do you work out the health contribution?"),
    ("What is the minimum wage this year?", "How much is the current minimum wage?"),
    ("Do I need to register for VAT?", "Is VAT registration mandatory for me?"),
    ("How do I issue a correction invoice?", "What is the process for a corrective invoice?"),
    ("What counts as a business expense?", "Which costs qualify as company expenses?"),
    ("How do I export a report to PDF?", "Can the report be saved as a PDF file?"),
    ("What are the opening hours of the shop?", "When is the shop open?"),
    ("How much stock of chicken is left?", "What is the remaining chicken inventory?"),
    ("How do I cancel an order?", "What is the way to cancel a placed order?"),
    ("What is the food cost percentage for kebab?", "What percentage of the kebab price is food cost?"),
    ("Where is the audit log stored?", "In which place are audit events kept?"),
    ("How do I rotate the API key?", "What is the procedure to replace the API key with a new one?"),
    ("Is the paid provider enabled?", "Are external paid models switched on?"),
    ("What is the daily budget for API calls?", "How much may be spent on the API per day?"),
    ("How do I upload a document for search?", "What is the way to add a file so it can be searched?"),
    ("Which file formats are supported for upload?", "What kinds of files can be uploaded?"),
    ("How do I check the status of a background task?", "Where can I see whether a queued job finished?"),
    ("What does INSUFFICIENT_CONTEXT mean?", "What is meant when the answer says INSUFFICIENT_CONTEXT?"),
    ("How many days are in February 2024?", "What is the number of days in February of 2024?"),
    ("Why did my request get rate limited?", "What is the reason my call returned a rate limit error?"),
    ("How is the confidence score computed?", "What goes into calculating the confidence value?"),
    ("Can RESTRICTED data be sent to an external provider?",
     "Is it allowed to send RESTRICTED information to outside APIs?"),
    ("What is a candidate solution?", "What does the CANDIDATE status of a solution mean?"),
    ("How do I promote a learned answer?", "What is the way to move a solution to PROMOTED?"),
    ("How do I restart the gateway service?", "What command restarts the gateway?"),
    ("What is the maximum request size?", "How large may a single request be?"),
]

UNRELATED = [
    ("What is the VAT rate in Poland?", "How do I bake sourdough bread at home?"),
    ("How are invoices numbered?", "Chess openings are classified by ECO code."),
    ("When is the contribution due?", "The train to Krakow leaves from platform four."),
    ("Explain the look-back rule and when it applies.", "Photosynthesis converts light to energy."),
    ("Who is allowed to approve an expense?", "The capital of France is Paris."),
    ("How do I reset my password?", "Mount Everest is the highest mountain on Earth."),
    ("What is the deadline for filing the monthly VAT return?", "Cats sleep for most of the day."),
    ("Can I deduct a laptop bought for the business?", "The Baltic Sea is brackish."),
    ("How long should invoices be kept?", "Jazz originated in New Orleans."),
    ("What happens if I pay ZUS late?", "Basil grows best in full sun."),
    ("How do I add a new user to the system?", "The marathon distance is 42.195 km."),
    ("Why is the server returning a 502 error?", "Honey never spoils."),
    ("How do I back up the database?", "The Moon orbits the Earth every 27 days."),
    ("Which port does the API listen on?", "Tulips were once worth more than houses."),
    ("How is the health contribution calculated under the flat tax?", "Octopuses have three hearts."),
    ("What is the minimum wage this year?", "The violin has four strings."),
    ("Do I need to register for VAT?", "Penguins live in the Southern Hemisphere."),
    ("How do I issue a correction invoice?", "Water boils at 100 degrees Celsius at sea level."),
    ("What counts as a business expense?", "The Great Wall of China is thousands of kilometres long."),
    ("How do I export a report to PDF?", "Sharks have existed longer than trees."),
    ("What are the opening hours of the shop?", "Saturn's rings are made mostly of ice."),
    ("How much stock of chicken is left?", "The Nile flows north."),
    ("How do I cancel an order?", "Bamboo can grow almost a metre in a day."),
    ("What is the food cost percentage for kebab?", "Light takes eight minutes to reach Earth from the Sun."),
    ("Where is the audit log stored?", "A group of crows is called a murder."),
    ("How do I rotate the API key?", "The Danube flows through ten countries."),
    ("Is the paid provider enabled?", "Bees communicate by dancing."),
    ("What is the daily budget for API calls?", "Iceland has no mosquitoes."),
    ("How do I upload a document for search?", "Venus rotates backwards."),
    ("Which file formats are supported for upload?", "Sloths can hold their breath for forty minutes."),
    ("How do I check the status of a background task?", "Bananas are botanically berries."),
    ("What does INSUFFICIENT_CONTEXT mean?", "The Sahara was once green."),
    ("How many days are in February 2024?", "Koalas sleep twenty hours a day."),
    ("Why did my request get rate limited?", "Chocolate was once used as currency."),
    ("How is the confidence score computed?", "Owls cannot move their eyes."),
    ("Can RESTRICTED data be sent to an external provider?", "The piano has eighty-eight keys."),
    ("What is a candidate solution?", "Norway has more than a thousand fjords."),
    ("How do I promote a learned answer?", "Sound cannot travel through a vacuum."),
    ("How do I restart the gateway service?", "The cheetah is the fastest land animal."),
    ("What is the maximum request size?", "Glass is made from sand."),
]

# Same question, one answer-changing detail swapped. Reusing the first
# question's stored answer for the second would be WRONG.
HARD_NEGATIVE = [
    ("What is the VAT rate in Poland?", "What is the VAT rate in Germany?"),
    ("What is the VAT rate in Poland?", "What is the PIT rate in Poland?"),
    ("How is the health contribution calculated under the flat tax?",
     "How is the health contribution calculated under the tax scale?"),
    ("What is the minimum wage in 2025?", "What is the minimum wage in 2026?"),
    ("When is the ZUS contribution due?", "When is the VAT payment due?"),
    ("Can I deduct a laptop bought for the business?", "Can I deduct a car bought for the business?"),
    ("How long should invoices be kept?", "How long should payslips be kept?"),
    ("What happens if I pay ZUS late?", "What happens if I pay ZUS early?"),
    ("Which port does the API listen on?", "Which port does the database listen on?"),
    ("How do I back up the database?", "How do I restore the database?"),
    ("How do I add a new user to the system?", "How do I remove a user from the system?"),
    ("Is VAT registration mandatory above the turnover limit?",
     "Is VAT registration mandatory below the turnover limit?"),
    ("What is the deadline for the monthly VAT return?", "What is the deadline for the quarterly VAT return?"),
    ("What is the food cost percentage for kebab?", "What is the food cost percentage for pizza?"),
    ("How much stock of chicken is left?", "How much stock of beef is left?"),
    ("What are the opening hours on Monday?", "What are the opening hours on Sunday?"),
    ("How do I issue a correction invoice?", "How do I issue a proforma invoice?"),
    ("Who is allowed to approve an expense?", "Who is allowed to reject an expense?"),
    ("Can RESTRICTED data be sent to an external provider?",
     "Can INTERNAL data be sent to an external provider?"),
    ("What is the daily budget for API calls?", "What is the monthly budget for API calls?"),
    ("How do I rotate the API key?", "How do I revoke the API key?"),
    ("How do I promote a learned answer?", "How do I reject a learned answer?"),
    ("How many days are in February 2024?", "How many days are in February 2023?"),
    ("What is 12% of 1200?", "What is 23% of 1200?"),
    ("How do I export a report to PDF?", "How do I export a report to CSV?"),
    ("What is the maximum request size?", "What is the minimum request size?"),
    ("Is the paid provider enabled?", "Is the paid provider disabled?"),
    ("Why is the server returning a 502 error?", "Why is the server returning a 404 error?"),
    ("How is the confidence score computed?", "How is the cost estimate computed?"),
    ("What is the health contribution rate for the flat tax?",
     "What is the health contribution rate for ryczałt?"),
    ("What is the deadline for PIT-36 in 2025?", "What is the deadline for PIT-28 in 2025?"),
    ("How do I cancel an order?", "How do I refund an order?"),
    ("What is the social contribution base for a new business?",
     "What is the social contribution base for an established business?"),
    ("Does the Fundusz Pracy apply on the preferential ZUS scheme?",
     "Does the Fundusz Pracy apply on the full ZUS scheme?"),
    ("How do I upload a PDF document?", "How do I delete a PDF document?"),
    ("What is the rate of the reduced VAT for food?", "What is the rate of the reduced VAT for books?"),
    ("How do I restart the gateway service?", "How do I stop the gateway service?"),
    ("What is the invoice numbering scheme for sales?", "What is the invoice numbering scheme for purchases?"),
    ("Which file formats are supported for upload?", "Which file formats are supported for export?"),
    ("How do I check the status of task A12?", "How do I check the status of task B34?"),
]

CANDIDATE_REUSE = [0.80, 0.78, 0.76, 0.74, 0.72, 0.70, 0.69, 0.65]
CANDIDATE_MEMORY = [0.72, 0.70, 0.65, 0.60, 0.55]
LEXICAL_WITNESS = 0.25  # app/memory/retrieval.py: a vector hit needs jaccard >= 0.25


def score(embedder, pairs):
    out = []
    for a, b in pairs:
        va, vb = embedder.embed([a, b])
        out.append({"a": a, "b": b, "cos": cosine(va, vb), "jaccard": jaccard(a, b)})
    return out


def summarise(name, rows):
    values = sorted(r["cos"] for r in rows)
    q = statistics.quantiles(values, n=10) if len(values) >= 10 else values
    return {
        "population": name,
        "n": len(values),
        "min": round(values[0], 4),
        "p10": round(q[0], 4),
        "median": round(statistics.median(values), 4),
        "p90": round(q[-1], 4),
        "max": round(values[-1], 4),
    }


def main() -> int:
    url = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
    model = os.environ.get("EMBEDDING_MODEL", "nomic-embed-text")
    embedder = OllamaEmbedder(OllamaClient(url, timeout=120), model, 768)

    related = score(embedder, RELATED)
    unrelated = score(embedder, UNRELATED)
    hard = score(embedder, HARD_NEGATIVE)

    report = {
        "embedder": embedder.id,
        "dimensions": embedder.dim,
        "populations": [
            summarise("related (paraphrase)", related),
            summarise("unrelated", unrelated),
            summarise("hard negative (one detail swapped)", hard),
        ],
        "reuse_gate": [],
        "memory_gate": [],
    }

    # Solution reuse: BOTH witnesses, as retrieval.py applies them.
    for t in CANDIDATE_REUSE:
        reused_ok = sum(1 for r in related if r["cos"] >= t and r["jaccard"] >= LEXICAL_WITNESS)
        reused_bad = sum(1 for r in hard if r["cos"] >= t and r["jaccard"] >= LEXICAL_WITNESS)
        reused_unrel = sum(1 for r in unrelated if r["cos"] >= t and r["jaccard"] >= LEXICAL_WITNESS)
        report["reuse_gate"].append(
            {
                "threshold": t,
                "paraphrases_reused": f"{reused_ok}/{len(related)}",
                "hard_negatives_wrongly_reused": f"{reused_bad}/{len(hard)}",
                "unrelated_wrongly_reused": f"{reused_unrel}/{len(unrelated)}",
            }
        )
    # Memory/document retrieval: cosine only (context is offered to the
    # model as evidence, not served as the answer).
    for t in CANDIDATE_MEMORY:
        found = sum(1 for r in related if r["cos"] >= t)
        noise = sum(1 for r in unrelated if r["cos"] >= t)
        report["memory_gate"].append(
            {
                "threshold": t,
                "paraphrases_retrieved": f"{found}/{len(related)}",
                "unrelated_retrieved": f"{noise}/{len(unrelated)}",
            }
        )

    # The pairs the thresholds turn on.
    report["lowest_related"] = sorted(related, key=lambda r: r["cos"])[:8]
    report["highest_unrelated"] = sorted(unrelated, key=lambda r: -r["cos"])[:5]
    report["highest_hard_negative"] = sorted(hard, key=lambda r: -r["cos"])[:12]
    for key in ("lowest_related", "highest_unrelated", "highest_hard_negative"):
        report[key] = [
            {**r, "cos": round(r["cos"], 4), "jaccard": round(r["jaccard"], 3)} for r in report[key]
        ]

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

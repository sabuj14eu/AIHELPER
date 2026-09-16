"""The deterministic agent router.

Four specialists existed and nothing sent a message to any of them: the agent
was whatever the dropdown held. These tests fix what "picks the right one"
means, and they are written so the router's accuracy is a measurement rather
than an opinion -- LABELLED is the set to grow when it gets something wrong.
"""

from __future__ import annotations

import pytest

from app.agents.builtin import build_agent_registry
from app.agents.router import MIN_SIGNALS, route_agent, score_domains

REGISTRY = build_agent_registry()


# (message, expected agent). "brother" means "no specialist clearly owns this",
# which is a correct answer, not a miss.
LABELLED: list[tuple[str, str]] = [
    # --- trading
    ("Gold now 4265 what is trading plan. today fomc", "trading"),
    ("Gold at 4346, FOMC in a few minutes, what is the plan?", "trading"),
    ("should we be careful with gold this session?", "trading"),
    ("what is the win rate on silver over the last month", "trading"),
    ("did the v7 bot take any trades in the asia session", "trading"),
    ("is the pullback entry still validated or has the profit factor dropped", "trading"),
    ("us100 broke structure, does the outlook still hold", "trading"),
    ("what does the council do when a signal has a low grade", "trading"),
    # --- architecture / engineering
    ("why does the chat endpoint return a 502 after a deploy", "architect"),
    ("the alembic migration failed on startup, what is the root cause", "architect"),
    ("refactor the retrieval module so the namespace is scoped", "architect"),
    ("pytest is failing on the knowledge pack tests after my change", "architect"),
    ("what is the deploy ceremony for the docker compose stack", "architect"),
    ("explain the database schema for the solutions table", "architect"),
    # --- social
    ("draft a linkedin post about the system", "social"),
    ("write a thread about what I learned building this", "social"),
    ("give me a caption for the youtube video", "social"),
    # --- a social post that is *about* trading is still social
    ("write a post about the gold trades this week", "social"),
    # --- generalist: nothing points anywhere
    ("hello", "brother"),
    ("hi bro how are you", "brother"),
    ("what did we talk about yesterday", "brother"),
    ("thanks, that helps", "brother"),
    ("what is the capital of France?", "brother"),
    ("remind me what the freshness law says", "brother"),
]


class TestRoutingAccuracy:
    @pytest.mark.parametrize("message,expected", LABELLED)
    def test_the_labelled_set_routes_correctly(self, message, expected):
        choice = route_agent(message, REGISTRY)
        assert choice.name == expected, f"{message!r} → {choice.name} ({choice.reason})"

    def test_every_decision_says_why(self):
        for message, _ in LABELLED:
            assert route_agent(message, REGISTRY).reason, message

    def test_a_miss_falls_back_to_the_generalist_never_to_nothing(self):
        """The fallback is what makes being wrong cheap.

        A miss costs one local call against a slightly wrong prompt. That is
        only true while the fallback is an agent that carries the client's
        whole tool set -- never "no agent", never a refusal.
        """
        for message in ("", "   ", "?", "asdfghjkl", "🙂"):
            choice = route_agent(message, REGISTRY)
            assert choice.name == "brother"
            assert REGISTRY.get(choice.name) is not None


class TestRoutingRules:
    def test_one_incidental_word_does_not_move_the_message(self):
        """"plan" alone is not a trading question; the floor is MIN_SIGNALS."""
        choice = route_agent("what is your plan for this conversation", REGISTRY)
        assert choice.name == "brother"
        assert MIN_SIGNALS >= 2

    def test_a_tie_goes_to_the_generalist(self):
        scores = score_domains("deploy the bot and write a post about the trade")
        top = sorted(scores.values(), reverse=True)
        if top and len(top) > 1 and top[0][0] == top[1][0] and top[0][0] >= MIN_SIGNALS:
            assert route_agent(
                "deploy the bot and write a post about the trade", REGISTRY
            ).name == "brother"

    def test_an_explicit_choice_is_never_overridden(self):
        """Someone who picked the social agent for a gold question meant it."""
        from app.agents.router import resolve_requested

        spec, choice = resolve_requested("social", "what is the gold plan today", REGISTRY)
        assert spec is not None and spec.name == "social"
        assert choice is None, "an explicit choice is not a routing decision"

    def test_auto_routes_and_reports_the_decision(self):
        from app.agents.router import resolve_requested

        spec, choice = resolve_requested("auto", "what is the gold plan for today", REGISTRY)
        assert spec is not None and spec.name == "trading"
        assert choice is not None and choice.score >= MIN_SIGNALS
        assert choice.as_dict()["agent"] == "trading"

    def test_a_disabled_specialist_falls_back_rather_than_failing(self):
        from app.agents.base import AgentRegistry
        from app.agents.builtin import BROTHER, TRADING

        registry = AgentRegistry([BROTHER, TRADING.__class__(**{**TRADING.__dict__, "enabled": False})])
        choice = route_agent("what is the gold plan today, fomc is on", registry)
        assert choice.name == "brother"

    def test_no_model_is_consulted(self):
        """Iron Rule 2: routing is a control decision and stays deterministic.

        The module imports nothing that can reach a provider; if that ever
        changes, this fails and the rule gets an explicit conversation.
        """
        from pathlib import Path

        import app.agents.router as router_module

        assert "not a model call" in (router_module.__doc__ or "")
        text = Path(router_module.__file__).read_text()
        body = text.split('"""', 2)[-1]  # skip the module docstring
        for word in ("provider", "ollama", "complete(", "anthropic"):
            assert word not in body.lower(), word

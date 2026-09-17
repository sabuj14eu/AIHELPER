"""The privacy gate on tools that reach the public internet.

A web search sends the question text to a third party. That is the same class
of act as a paid provider call, and the privacy architecture has governed that
since 1.0 -- but nothing connected the two. `may_leave_system` was called from
exactly one place, `escalation.may_escalate`, so the rule "RESTRICTED data may
never be sent to an external provider" would not have been consulted when
Brother typed a RESTRICTED question into a search box.

These tests are the connection, and the first one is the whole point.
"""

from __future__ import annotations

import pytest

from app.database.enums import Classification
from app.tools.builder import build_registry
from app.tools.egress import may_use_network, network_tool_names, permissions_for
from app.tools.registry import DEFAULT_PERMISSIONS, PERM_NETWORK


@pytest.fixture
def registry(settings):
    settings.WEB_SEARCH_ENABLED = True
    settings.WEB_SEARCH_URL = "http://searxng:8080/search"
    return build_registry(settings)


def _decide(settings, registry, *, classification, tools, ceiling=None):
    return may_use_network(
        classification=classification,
        settings=settings,
        client_allowed_tools=tools,
        client_max_classification=ceiling,
        registry=registry,
    )


class TestRestrictedNeverLeaves:
    def test_restricted_is_refused_even_with_every_permission_granted(
        self, settings, registry
    ):
        """The one that matters. No configuration may override this."""
        decision = _decide(
            settings, registry,
            classification=Classification.RESTRICTED,
            tools=["web_search", "calculator"],
        )
        assert decision.allowed is False
        assert "RESTRICTED" in decision.reason

    def test_the_permission_set_withholds_the_network_bit(self, settings, registry):
        permissions, decision = permissions_for(
            classification=Classification.RESTRICTED,
            settings=settings,
            client_allowed_tools=["web_search"],
            client_max_classification=None,
            registry=registry,
        )
        assert PERM_NETWORK not in permissions
        assert decision.allowed is False

    def test_a_client_ceiling_below_the_data_still_refuses(self, settings, registry):
        decision = _decide(
            settings, registry,
            classification=Classification.CONFIDENTIAL,
            tools=["web_search"],
            ceiling="PUBLIC",
        )
        assert decision.allowed is False

    def test_it_is_the_same_gate_the_paid_path_uses(self):
        """One policy, not two that drift apart.

        If this import ever stops being the shared function, the two egress
        paths can disagree about what may leave, and only one of them will be
        the one anybody remembers to update.
        """
        import app.gateway.escalation as escalation
        import app.tools.egress as egress

        assert egress.may_leave_system is escalation.may_leave_system


class TestGrantingIsExplicit:
    def test_the_floor_is_no_network(self):
        assert PERM_NETWORK not in DEFAULT_PERMISSIONS

    def test_inheriting_every_tool_does_not_grant_the_internet(self, settings, registry):
        """`allowed_tools = None` means "not narrowed", which is not consent."""
        decision = _decide(
            settings, registry, classification=Classification.INTERNAL, tools=None
        )
        assert decision.allowed is False
        assert "not the same as choosing" in decision.reason

    def test_a_tool_list_without_a_network_tool_does_not_grant_it(self, settings, registry):
        decision = _decide(
            settings, registry,
            classification=Classification.INTERNAL,
            tools=["calculator", "document_search"],
        )
        assert decision.allowed is False

    def test_naming_the_tool_grants_it_for_permitted_data(self, settings, registry):
        decision = _decide(
            settings, registry,
            classification=Classification.INTERNAL,
            tools=["web_search", "calculator"],
        )
        assert decision.allowed is True
        assert "web_search" in decision.reason

        permissions, _ = permissions_for(
            classification=Classification.INTERNAL,
            settings=settings,
            client_allowed_tools=["web_search"],
            client_max_classification=None,
            registry=registry,
        )
        assert PERM_NETWORK in permissions

    def test_a_disabled_network_tool_still_counts_as_a_network_tool(self, settings):
        """The question is "would granting this let the request leave?", and a
        tool that is off today can be on tomorrow."""
        settings.WEB_SEARCH_ENABLED = False
        off = build_registry(settings)
        assert "web_search" in network_tool_names(off)

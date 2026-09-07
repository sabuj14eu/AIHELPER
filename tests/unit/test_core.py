"""Configuration, credentials and log redaction."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.core.logging import _redact, scrub_text
from app.core.security import (
    create_session_token,
    generate_api_key,
    hash_password,
    parse_api_key,
    verify_api_key,
    verify_password,
    verify_session_token,
)


class TestSettings:
    def test_paid_providers_are_off_by_default(self):
        settings = Settings()
        assert settings.OPENAI_ENABLED is False
        assert settings.ANTHROPIC_ENABLED is False
        assert settings.any_paid_provider_configured() is False

    def test_budgets_always_have_a_finite_default(self):
        settings = Settings()
        assert settings.AI_DAILY_API_BUDGET > 0
        assert settings.AI_MONTHLY_API_BUDGET > 0
        assert settings.AI_MAX_COST_PER_REQUEST > 0

    def test_restricted_can_never_be_configured_as_externally_allowed(self):
        with pytest.raises(ValueError, match="RESTRICTED"):
            Settings(EXTERNAL_ALLOWED_CLASSIFICATIONS="PUBLIC,INTERNAL,RESTRICTED")

    def test_external_allowed_parses_to_a_set(self):
        settings = Settings(EXTERNAL_ALLOWED_CLASSIFICATIONS=" public , internal ")
        assert settings.external_allowed == {"PUBLIC", "INTERNAL"}

    def test_an_enabled_provider_without_a_key_is_not_configured(self):
        assert Settings(OPENAI_ENABLED=True).any_paid_provider_configured() is False
        assert (
            Settings(OPENAI_ENABLED=True, OPENAI_API_KEY="sk-x").any_paid_provider_configured()
            is True
        )


class TestApiKeys:
    def test_round_trip(self):
        key = generate_api_key()
        assert key.plaintext.startswith("ahk_")
        assert verify_api_key(key.plaintext, key.hashed)
        assert parse_api_key(key.plaintext) == key.key_id

    def test_the_plaintext_is_not_recoverable_from_the_hash(self):
        key = generate_api_key()
        assert key.secret not in key.hashed
        assert len(key.hashed) == 64

    def test_a_wrong_secret_with_a_right_key_id_fails(self):
        key = generate_api_key()
        forged = f"ahk_{key.key_id}.wrong-secret-entirely"
        assert verify_api_key(forged, key.hashed) is False

    @pytest.mark.parametrize("bad", ["", "nonsense", "ahk_only", "ahk_.secret", "bearer x"])
    def test_malformed_keys_are_rejected(self, bad):
        assert parse_api_key(bad) is None

    def test_two_keys_never_collide(self):
        assert len({generate_api_key().plaintext for _ in range(50)}) == 50


class TestPasswords:
    def test_round_trip(self):
        stored = hash_password("a long enough password")
        assert verify_password("a long enough password", stored)
        assert not verify_password("something else", stored)

    def test_the_same_password_hashes_differently_each_time(self):
        assert hash_password("same") != hash_password("same")

    @pytest.mark.parametrize("stored", [None, "", "garbage", "scrypt$bad", "a$b$c$d$e$f"])
    def test_a_corrupt_stored_hash_never_verifies(self, stored):
        assert verify_password("anything", stored) is False

    def test_a_password_longer_than_72_bytes_works(self):
        """bcrypt's 72-byte ceiling is why this codebase uses scrypt."""
        long_password = "x" * 200
        assert verify_password(long_password, hash_password(long_password))


class TestSessionTokens:
    def test_round_trip(self):
        token = create_session_token("admin", "secret", 30)
        assert verify_session_token(token, "secret")["sub"] == "admin"

    def test_a_different_secret_does_not_verify(self):
        token = create_session_token("admin", "secret", 30)
        assert verify_session_token(token, "other-secret") is None

    def test_an_expired_token_does_not_verify(self):
        assert verify_session_token(create_session_token("admin", "s", -1), "s") is None

    def test_a_tampered_payload_does_not_verify(self):
        token = create_session_token("admin", "s", 30)
        head, payload, signature = token.split(".")
        assert verify_session_token(f"{head}.{payload}x.{signature}", "s") is None

    @pytest.mark.parametrize("bad", ["", "a.b", "not-a-token", "a.b.c.d"])
    def test_malformed_tokens_are_rejected(self, bad):
        assert verify_session_token(bad, "s") is None


class TestRedaction:
    def test_sensitive_keys_are_replaced(self):
        out = _redact({"api_key": "sk-real", "nested": {"password": "hunter2", "count": 3}})
        assert out["api_key"] == "[REDACTED]"
        assert out["nested"]["password"] == "[REDACTED]"
        assert out["nested"]["count"] == 3

    def test_message_bodies_are_never_logged(self):
        out = _redact({"message": "confidential question", "prompt": "x", "answer": "y"})
        assert set(out.values()) == {"[REDACTED]"}

    @pytest.mark.parametrize(
        "text",
        [
            "sk-abcdefghijklmnopqrstuvwxyz",
            "sk-ant-abcdefghijklmnopqrstuvwx",
            "Bearer abcdefghijklmnopqrst",
            "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhZG1pbiJ9.c2lnbmF0dXJlaGVyZQ",
        ],
    )
    def test_secrets_in_free_text_are_scrubbed(self, text):
        assert "[REDACTED]" in scrub_text(f"the value is {text} ok")

    def test_deep_structures_do_not_recurse_forever(self):
        deep: dict = {}
        node = deep
        for _ in range(50):
            node["next"] = {}
            node = node["next"]
        assert _redact(deep) is not None


class TestLogDestination:
    def test_logs_go_to_stderr_so_stdout_stays_machine_readable(self, capsys):
        from app.core.logging import configure_logging, get_logger

        configure_logging("INFO", "json")
        print("machine-readable output")
        get_logger("t").info("a log line", detail="x")
        captured = capsys.readouterr()
        assert captured.out.strip() == "machine-readable output"
        assert "a log line" in captured.err

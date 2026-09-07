"""Regression tests for the container image contract.

Added after the audit found the build could not complete on a host without
access to Debian's package repositories. The apt layers turned out to be
unnecessary — every dependency is a pre-built wheel, psycopg[binary] bundles
its own libpq, and useradd is in the base image — so they were removed. These
tests keep them out, because reintroducing one would silently reattach the
build to a network resource it does not need.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = (ROOT / "Dockerfile").read_text()
REQUIREMENTS = (ROOT / "requirements.txt").read_text()


class TestDockerfile:
    def test_the_build_needs_no_package_repository(self):
        offenders = [
            line.strip()
            for line in DOCKERFILE.splitlines()
            if re.search(r"\b(apt-get|apt |apk |yum |dnf )\b", line)
            and not line.strip().startswith("#")
        ]
        assert offenders == [], (
            "the image build reaches a package repository again: "
            f"{offenders}. Every runtime dependency is a wheel and psycopg[binary] "
            "bundles libpq — if something genuinely needs a system package, add it "
            "to the BUILDER stage and say why."
        )

    def test_dependencies_are_installed_as_wheels_only(self):
        """--only-binary=:all: makes a build that would need a compiler fail
        loudly, instead of silently requiring a toolchain the image lacks."""
        assert "--only-binary=:all:" in DOCKERFILE

    def test_the_healthcheck_uses_the_interpreter_already_present(self):
        assert "HEALTHCHECK" in DOCKERFILE
        healthcheck = DOCKERFILE[DOCKERFILE.index("HEALTHCHECK"):]
        assert "curl" not in healthcheck.split("CMD")[0] + healthcheck.split("CMD")[1][:200], (
            "the healthcheck depends on curl, which means the image carries a "
            "package purely to check itself"
        )
        assert "/healthz" in healthcheck, "the healthcheck must probe liveness, not /health"

    def test_the_container_does_not_run_as_root(self):
        users = re.findall(r"^USER\s+(\S+)", DOCKERFILE, re.M)
        assert users, "the image never drops root"
        assert users[-1] != "root"

    def test_a_custom_ca_is_a_build_secret_not_a_layer(self):
        """A certificate copied into a layer ships with the image and outlives
        the build. Behind a TLS-intercepting proxy it must be a secret mount."""
        assert "--mount=type=secret" in DOCKERFILE
        assert not re.search(r"^COPY\b.*\.crt", DOCKERFILE, re.M), (
            "a certificate is being COPYed into an image layer"
        )

    def test_the_build_is_multi_stage_so_build_tooling_never_ships(self):
        assert len(re.findall(r"^FROM ", DOCKERFILE, re.M)) >= 2
        assert "--from=builder" in DOCKERFILE

    @pytest.mark.parametrize("path", ["alembic.ini", "app", "scripts", "requirements.txt"])
    def test_everything_the_image_copies_exists(self, path):
        assert path in DOCKERFILE, f"{path} is no longer copied into the image"
        assert (ROOT / path).exists(), f"{path} is copied but missing from the repository"


class TestRequirements:
    def test_no_compiler_only_dependency_crept_in(self):
        """A source-only dependency would break the wheel-only build. The
        packages listed here all publish manylinux wheels for CPython 3.11."""
        assert "psycopg[binary]" in REQUIREMENTS, (
            "psycopg[binary] bundles libpq; plain psycopg would need the system "
            "library the image deliberately does not install"
        )

    def test_no_password_hashing_library_returned(self):
        """scrypt from the standard library, on purpose — see app/core/security.py.

        Reads the requirement lines only: the file carries a comment explaining
        why passlib is absent, and a naive substring check trips over it.
        """
        requirements = [
            line.split("#")[0].strip()
            for line in REQUIREMENTS.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        offenders = [r for r in requirements if re.match(r"(?i)^(passlib|bcrypt)\b", r)]
        assert offenders == [], f"a password-hashing dependency is back: {offenders}"


class TestComposeFile:
    """Regression tests for docker-compose.yml.

    Added after the audit found n8n crash-looping forever on an IPv4-only host
    while `docker compose ps` cheerfully reported the container as Up.
    """

    COMPOSE = (ROOT / "docker-compose.yml").read_text()

    def test_n8n_binds_an_address_that_exists_on_an_ipv4_only_host(self):
        """n8n defaults to binding "::". Where there is no IPv6 that fails, and
        `restart: unless-stopped` turns the failure into an endless loop."""
        assert "N8N_LISTEN_ADDRESS" in self.COMPOSE, (
            "n8n has no explicit listen address, so it will bind :: and "
            "crash-loop on any host without IPv6"
        )
        assert "N8N_LISTEN_ADDRESS: 0.0.0.0" in self.COMPOSE

    def test_every_stateful_service_has_a_named_volume(self):
        for service in ("postgres", "qdrant", "ollama", "n8n"):
            assert f"{service}_data" in self.COMPOSE or f"{service}_models" in self.COMPOSE, (
                f"{service} keeps state in the container's writable layer, so "
                "`docker compose down` destroys it"
            )

    def test_nothing_is_published_beyond_loopback(self):
        published = re.findall(r'^\s+- "([^"]+:)?(\d+):(\d+)"', self.COMPOSE, re.M)
        exposed = [p for p in published if p[0] not in ("127.0.0.1:",)]
        assert exposed == [], (
            f"these ports are published on all interfaces: {exposed}. "
            "Put a TLS-terminating proxy in front instead."
        )

    def test_the_database_publishes_no_port_at_all(self):
        postgres_block = self.COMPOSE[self.COMPOSE.index("  postgres:"):]
        postgres_block = postgres_block[:postgres_block.index("\n  qdrant:")]
        assert "ports:" not in postgres_block, (
            "the production compose publishes a database port; nothing outside "
            "the compose network needs it"
        )

    def test_secrets_have_no_usable_default(self):
        for variable in ("POSTGRES_PASSWORD", "N8N_ENCRYPTION_KEY", "WEBUI_SECRET_KEY"):
            assert f"${{{variable}:?" in self.COMPOSE, (
                f"{variable} has a silent default; compose should refuse to start without it"
            )

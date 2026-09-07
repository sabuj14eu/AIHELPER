"""Qdrant backend, embedder selection, the job runner, the CLI and the limiter."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from app.api.ratelimit import TokenBucketLimiter
from app.memory.embeddings import HashingEmbedder, build_embedder
from app.memory.semantic import QdrantVectorStore


class TestQdrantStore:
    """Exercised against a mock: the contract is that every query carries the
    client filter, and that a payload from the wrong client is dropped even if
    the filter did not do its job."""

    def _store(self):
        client = MagicMock()
        client.collection_exists.return_value = False
        return QdrantVectorStore(client, dim=8), client

    def test_a_collection_is_created_once_with_the_right_dimension(self):
        store, client = self._store()
        store.upsert(
            collection="c", point_id="p1", client_id="a", vector=[0.0] * 8, ref_type="m", ref_id="x"
        )
        store.upsert(
            collection="c", point_id="p2", client_id="a", vector=[0.0] * 8, ref_type="m", ref_id="y"
        )
        assert client.create_collection.call_count == 1
        assert client.create_collection.call_args.kwargs["vectors_config"].size == 8

    def test_the_client_id_is_written_into_every_payload(self):
        store, client = self._store()
        store.upsert(
            collection="c",
            point_id="p1",
            client_id="alpha",
            vector=[0.0] * 8,
            ref_type="memory",
            ref_id="m1",
            payload={"kind": "fact"},
        )
        point = client.upsert.call_args.kwargs["points"][0]
        assert point.payload["client_id"] == "alpha"
        assert point.payload["ref_id"] == "m1"
        assert point.payload["kind"] == "fact"

    def test_search_filters_on_the_client_id_in_the_query(self):
        store, client = self._store()
        client.query_points.return_value.points = []
        store.search(collection="c", client_id="alpha", vector=[0.0] * 8)
        conditions = client.query_points.call_args.kwargs["query_filter"].must
        assert any(
            c.key == "client_id" and c.match.value == "alpha" for c in conditions
        ), "the client filter was not applied in the query"

    def test_a_point_from_the_wrong_client_is_dropped_even_if_the_filter_failed(self):
        """Belt and braces: a filter bug must not become a data leak."""
        store, client = self._store()
        leaked = MagicMock()
        leaked.payload = {"client_id": "beta", "ref_type": "memory", "ref_id": "b1"}
        leaked.score = 0.99
        client.query_points.return_value.points = [leaked]
        assert store.search(collection="c", client_id="alpha", vector=[0.0] * 8) == []

    def test_health_reports_failure_without_raising(self):
        store, client = self._store()
        client.get_collections.side_effect = RuntimeError("down")
        assert store.healthy() is False

    def test_point_ids_are_deterministic_uuids(self):
        assert QdrantVectorStore._point_uuid("sol:abc") == QdrantVectorStore._point_uuid("sol:abc")
        assert QdrantVectorStore._point_uuid("sol:abc") != QdrantVectorStore._point_uuid("sol:abd")


class TestEmbedderSelection:
    def test_the_lexical_fallback_is_used_when_no_model_is_installed(self, settings):
        manager = MagicMock()
        manager.select_embedding_model.return_value = None
        embedder = build_embedder(manager, MagicMock(), configured_dim=768)
        assert isinstance(embedder, HashingEmbedder)
        assert embedder.semantic is False

    def test_a_working_model_is_preferred(self, settings):
        manager = MagicMock()
        manager.select_embedding_model.return_value = "nomic-embed-text"
        client = MagicMock()
        client.embed.return_value = [[0.1] * 768]
        embedder = build_embedder(manager, client, configured_dim=768)
        assert embedder.semantic is True and embedder.id == "ollama-nomic-embed-text"

    def test_a_model_that_errors_on_probe_falls_back_rather_than_failing_startup(self, settings):
        manager = MagicMock()
        manager.select_embedding_model.return_value = "nomic-embed-text"
        client = MagicMock()
        client.embed.side_effect = RuntimeError("model is not loaded")
        assert build_embedder(manager, client).semantic is False

    def test_the_real_dimension_wins_over_the_configured_one(self, settings):
        from app.memory.embeddings import OllamaEmbedder

        client = MagicMock()
        client.embed.return_value = [[0.1] * 384]
        embedder = OllamaEmbedder(client, "some-model", dim=768)
        embedder.embed(["probe"])
        assert embedder.dim == 384

    def test_a_wrong_vector_count_is_an_error(self, settings):
        from app.memory.embeddings import OllamaEmbedder

        client = MagicMock()
        client.embed.return_value = [[0.1] * 8]
        with pytest.raises(ValueError):
            OllamaEmbedder(client, "m", dim=8).embed(["a", "b"])


class TestRateLimiter:
    def test_the_burst_is_the_capacity(self):
        limiter = TokenBucketLimiter(rate_per_minute=60, burst=3)
        assert [limiter.check("k").allowed for _ in range(5)] == [True, True, True, False, False]

    def test_a_per_client_override_changes_the_refill_rate(self):
        limiter = TokenBucketLimiter(rate_per_minute=1, burst=2)
        limiter.check("k")
        limiter.check("k")
        assert limiter.check("k", rate_override=6000).allowed is False  # capacity still 2
        limiter.reset("k")
        assert limiter.check("k", rate_override=6000).allowed is True

    def test_buckets_are_independent(self):
        limiter = TokenBucketLimiter(rate_per_minute=60, burst=1)
        assert limiter.check("a").allowed and limiter.check("b").allowed
        assert limiter.check("a").allowed is False

    def test_a_blocked_decision_says_when_to_retry(self):
        limiter = TokenBucketLimiter(rate_per_minute=60, burst=1)
        limiter.check("k")
        decision = limiter.check("k")
        assert decision.allowed is False and decision.retry_after > 0

    def test_reset_clears_everything(self):
        limiter = TokenBucketLimiter(rate_per_minute=60, burst=1)
        limiter.check("a")
        limiter.reset()
        assert limiter.check("a").allowed is True


class TestJobRunner:
    def test_an_unregistered_kind_is_refused(self, engine):
        from app.api.jobs import JobRunner

        runner = JobRunner(1)
        with pytest.raises(ValueError, match="no handler"):
            runner.submit(client_id="acme", kind="nope", payload={})
        runner.shutdown(wait=True)

    def test_a_failing_handler_is_recorded_as_failed_not_lost(self, engine):
        import time

        from app.api.jobs import JobRunner
        from app.database.models import Job
        from app.database.session import session_scope

        runner = JobRunner(1)
        runner.register("boom", lambda _c, _p: (_ for _ in ()).throw(RuntimeError("nope")))
        job_id = runner.submit(client_id="acme", kind="boom", payload={})
        for _ in range(200):
            with session_scope() as session:
                job = session.get(Job, job_id)
                status, error = job.status, job.error
            if status in ("succeeded", "failed"):
                break
            time.sleep(0.01)
        assert status == "failed" and "RuntimeError" in error
        runner.shutdown(wait=True)

    def test_orphaned_jobs_from_a_previous_process_are_marked_failed(self, engine, db):
        from app.api.jobs import JobRunner
        from app.database.enums import JobStatus
        from app.database.models import Job

        db.add(Job(id="task_orphan", client_id="acme", kind="chat", status=JobStatus.RUNNING.value))
        db.commit()
        runner = JobRunner(1)
        assert runner.recover_orphans() == 1
        db.expire_all()
        assert db.get(Job, "task_orphan").status == JobStatus.FAILED.value
        assert "restarted" in db.get(Job, "task_orphan").error
        runner.shutdown(wait=True)


class TestCli:
    def test_create_client_issues_a_key_once(self, engine, capsys, monkeypatch):
        from app import cli

        assert cli.main(["create-client", "acme", "--may-escalate"]) == 0
        printed = json.loads(capsys.readouterr().out)
        assert printed["client_id"] == "acme"
        assert printed["api_key"].startswith("ahk_")

        # The same id twice is refused rather than silently reissuing a key.
        assert cli.main(["create-client", "acme"]) == 2

    def test_hash_password_refuses_a_short_password(self, monkeypatch, capsys):
        from app import cli

        monkeypatch.setattr(cli.getpass, "getpass", lambda _prompt: "short")
        assert cli.main(["hash-password"]) == 2

    def test_hash_password_refuses_a_mismatch(self, monkeypatch):
        from app import cli

        entries = iter(["a-long-enough-password", "a-different-password"])
        monkeypatch.setattr(cli.getpass, "getpass", lambda _prompt: next(entries))
        assert cli.main(["hash-password"]) == 2

    def test_hash_password_emits_an_env_line(self, monkeypatch, capsys):
        from app import cli
        from app.core.security import verify_password

        monkeypatch.setattr(cli.getpass, "getpass", lambda _prompt: "a-long-enough-password")
        assert cli.main(["hash-password"]) == 0
        line = capsys.readouterr().out.strip()
        assert line.startswith("ADMIN_PASSWORD_HASH=")
        assert verify_password("a-long-enough-password", line.split("=", 1)[1])

    def test_expire_reports_what_it_aged_out(self, engine, capsys):
        from app import cli

        assert cli.main(["expire"]) == 0
        assert json.loads(capsys.readouterr().out) == {
            "solutions_expired": 0,
            "memory_expired": 0,
        }

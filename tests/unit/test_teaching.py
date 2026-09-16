"""Teaching: the owner's corrections go through the same gate as a paid answer."""

from __future__ import annotations

import json

from app.database.enums import Route, SolutionStatus
from app.gateway.router import GatewayRequest
from app.learning.solution_store import SolutionStore
from app.learning.teaching import teach

QUESTION = "What does the ZUS health contribution look-back rule say?"
ANSWER = (
    "Under the flat tax the health contribution for a month is 4.9% of the income of the "
    "month before it, and the contribution year runs from 1 February to 31 January."
)


class TestTeach:
    def test_a_taught_answer_is_promoted_and_then_answers_for_free(
        self, runtime, db, client_row, settings, local_provider, paid_provider
    ):
        services = runtime.for_session(db, client_row.client_id)
        result = teach(
            db, client_row.client_id, question=QUESTION, answer=ANSWER, actor="admin:shyam",
            settings=settings, local_provider=local_provider, retriever=services.retriever,
            evidence="modules/poland/config/rates/zus_health.php",
        )
        assert result.outcome.promoted, result.outcome.reason
        row = SolutionStore(db, client_row.client_id).get(result.solution_id)
        assert row.provider == "owner" and row.model == "admin:shyam"
        assert row.validation_result["taught"]["evidence"].startswith("modules/poland")
        assert row.status == SolutionStatus.PROMOTED.value

        # The local model could not answer this alone (it is a hard topic for the
        # fake); now the exact question is a memory hit, no paid call.
        response = services.router.handle(GatewayRequest(message=QUESTION, client=client_row))
        assert response.memory_hit and response.route is Route.LOCAL
        assert response.solution_id == result.solution_id
        assert paid_provider.call_count == 0

    def test_teaching_again_supersedes_the_earlier_answer(
        self, runtime, db, client_row, settings, local_provider
    ):
        services = runtime.for_session(db, client_row.client_id)
        first = teach(
            db, client_row.client_id, question=QUESTION, answer=ANSWER, actor="cli",
            settings=settings, local_provider=local_provider, retriever=services.retriever,
        )
        second = teach(
            db, client_row.client_id, question=QUESTION,
            answer=ANSWER + " January is settled on the previous year's figures.", actor="cli",
            settings=settings, local_provider=local_provider, retriever=services.retriever,
        )
        assert second.superseded == [first.solution_id]
        store = SolutionStore(db, client_row.client_id)
        assert store.get(first.solution_id).status == SolutionStatus.EXPIRED.value
        assert "superseded" in store.get(first.solution_id).status_reason
        assert services.retriever.find_exact_solution(QUESTION).id == second.solution_id

    def test_a_taught_answer_the_local_model_cannot_use_is_not_promoted(
        self, runtime, db, client_row, settings, local_provider
    ):
        local_provider.answer_override = "I cannot help with that."
        services = runtime.for_session(db, client_row.client_id)
        result = teach(
            db, client_row.client_id, question=QUESTION, answer=ANSWER, actor="cli",
            settings=settings, local_provider=local_provider, retriever=services.retriever,
        )
        assert result.outcome.status is SolutionStatus.REJECTED
        assert services.retriever.find_exact_solution(QUESTION) is None

    def test_an_empty_pair_is_refused(self, runtime, db, client_row, settings, local_provider):
        import pytest

        services = runtime.for_session(db, client_row.client_id)
        with pytest.raises(ValueError):
            teach(
                db, client_row.client_id, question=QUESTION, answer="", actor="cli",
                settings=settings, local_provider=local_provider, retriever=services.retriever,
            )


class TestTeachCli:
    def test_teach_from_the_terminal(self, runtime, engine, capsys, tmp_path):
        from app import cli
        from tests.unit.test_knowledge_pack import write_pack

        pack = write_pack(tmp_path / "pack")
        assert cli.main(["bootstrap-brother", "--path", str(pack), "--no-seed"]) == 0
        capsys.readouterr()
        assert cli.main(["teach", "--question", QUESTION, "--answer", ANSWER, "--evidence", "x"]) == 0
        out = json.loads(capsys.readouterr().out)
        assert out["promoted"] and out["status"] == "PROMOTED"
        assert cli.main(["teach", "--question", QUESTION, "--answer", "no"]) == 2

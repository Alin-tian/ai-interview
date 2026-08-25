import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api import interviews


class ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class ScalarsResult:
    def __init__(self, values):
        self.values = values

    def scalars(self):
        return self

    def first(self):
        return self.values[0] if self.values else None


@pytest.mark.asyncio
async def test_answer_lock_is_released_when_stream_is_cancelled(monkeypatch):
    session = SimpleNamespace(id=1, status="in_progress")
    turn = SimpleNamespace(id=2, answer=None, evaluation=None, question={})
    db = SimpleNamespace(execute=AsyncMock(return_value=ScalarResult(turn)), rollback=AsyncMock())
    release = AsyncMock()

    monkeypatch.setattr(interviews, "session_or_404", AsyncMock(return_value=session))
    monkeypatch.setattr(interviews, "acquire_answer_lock", AsyncMock(return_value=True))
    monkeypatch.setattr(interviews, "release_answer_lock", release)
    monkeypatch.setattr(interviews, "evaluate_turn", AsyncMock(side_effect=asyncio.CancelledError()))

    response = await interviews.submit_answer(1, {"turn_id": 2, "answer": "我的回答"}, db)
    iterator = response.body_iterator
    await iterator.__anext__()
    with pytest.raises(asyncio.CancelledError):
        await iterator.__anext__()

    release.assert_awaited_once_with(1, 2)


@pytest.mark.asyncio
async def test_persisted_evaluation_retries_only_the_next_step(monkeypatch):
    session = SimpleNamespace(id=1, status="in_progress", followups_for_round=0, current_round=1, max_rounds=10)
    turn = SimpleNamespace(id=2, answer="已保存的回答", evaluation={"overall_score": 80}, question={})
    db = SimpleNamespace(execute=AsyncMock(side_effect=[ScalarResult(turn), ScalarsResult([])]), rollback=AsyncMock())
    next_turn = SimpleNamespace(id=3, answer=None, evaluation=None, question={"question": "下一题"}, round_no=2, is_followup=False)
    evaluate = AsyncMock()
    advance = AsyncMock(return_value=(next_turn, None))

    monkeypatch.setattr(interviews, "session_or_404", AsyncMock(return_value=session))
    monkeypatch.setattr(interviews, "evaluate_turn", evaluate)
    monkeypatch.setattr(interviews, "plan_next", AsyncMock(return_value="new_question"))
    monkeypatch.setattr(interviews, "advance_interview", advance)

    response = await interviews.submit_answer(1, {"turn_id": 2, "answer": ""}, db)
    events = [chunk async for chunk in response.body_iterator]

    evaluate.assert_not_awaited()
    advance.assert_awaited_once_with(session, turn, "new_question", db)
    assert any("workflow_node_enter" in event and "next_step" in event for event in events)
    assert any("event: question" in event for event in events)

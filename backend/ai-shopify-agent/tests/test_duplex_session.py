import asyncio

import pytest

from app.voice.session import DuplexSession, SpeakingState


@pytest.mark.asyncio
async def test_cancel_pipeline_cancels_task_and_resets_interrupt():
    session = DuplexSession("test-session")

    async def long_running():
        await asyncio.sleep(10)

    task = asyncio.create_task(long_running())
    session.set_pipeline_task(task)
    session.mark_ai_speaking()

    await session.cancel_pipeline()

    assert session.state == SpeakingState.AI_SPEAKING
    assert session.interrupt.is_set() is False
    assert task.cancelled() or task.done()


def test_state_transitions():
    session = DuplexSession("state-session")

    assert session.state == SpeakingState.IDLE
    session.mark_user_speaking()
    assert session.state == SpeakingState.USER_SPEAKING

    session.mark_ai_speaking()
    assert session.ai_is_speaking is True

    session.mark_idle()
    assert session.state == SpeakingState.IDLE

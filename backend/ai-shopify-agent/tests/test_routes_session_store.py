import asyncio
import importlib

pytest = importlib.import_module("pytest")


@pytest.mark.asyncio
async def test_get_session_prunes_stale_unlocked_locks(monkeypatch):
    import app.api.routes as routes_mod

    routes_mod._active_sessions.clear()
    routes_mod._session_locks.clear()
    monkeypatch.setattr(routes_mod, "MAX_SESSION_LOCKS", 1)

    routes_mod._session_locks["stale-session"] = asyncio.Lock()
    await routes_mod._get_session("live-session")

    assert "live-session" in routes_mod._session_locks
    assert "stale-session" not in routes_mod._session_locks
    assert len(routes_mod._session_locks) == 1

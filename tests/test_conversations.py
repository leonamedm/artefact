from __future__ import annotations

from tests.conftest import NOW


def test_session_roundtrip(conversations):
    session = conversations.create_session(NOW)
    assert conversations.exists(session)
    conversations.append(session, [{"role": "user", "content": "Oi"}], NOW)
    conversations.append(session, [{"role": "assistant", "content": "Olá!"}], NOW)
    assert conversations.load(session) == [
        {"role": "user", "content": "Oi"},
        {"role": "assistant", "content": "Olá!"},
    ]
    assert not conversations.exists("missing")

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services import google_auth


class _Result:
    def __init__(self, user):
        self._user = user

    def scalar_one_or_none(self):
        return self._user


class _FakeCreds:
    def __init__(self, token=None, refresh_token=None, token_uri=None, client_id=None, client_secret=None, scopes=None):
        self.token = token
        self.refresh_token = refresh_token
        self.token_uri = token_uri
        self.client_id = client_id
        self.client_secret = client_secret
        self.scopes = scopes
        self.expired = True

    def refresh(self, _request):
        self.token = "new-token"


@pytest.mark.asyncio
async def test_get_user_credentials_returns_none_without_access_token(monkeypatch):
    user = SimpleNamespace(
        id=uuid4(),
        google_access_token=None,
        google_refresh_token=None,
    )

    class _DB:
        async def execute(self, _):
            return _Result(user)

    creds = await google_auth.get_user_credentials(user.id, db=_DB())
    assert creds is None


@pytest.mark.asyncio
async def test_get_user_credentials_refreshes_and_commits(monkeypatch):
    user = SimpleNamespace(
        id=uuid4(),
        google_access_token="old-token",
        google_refresh_token="refresh-token",
    )

    class _DB:
        committed = False

        async def execute(self, _):
            return _Result(user)

        async def commit(self):
            self.committed = True

    fake_db = _DB()

    monkeypatch.setattr(google_auth, "Credentials", _FakeCreds)
    monkeypatch.setattr(google_auth, "Request", lambda: object())

    creds = await google_auth.get_user_credentials(user.id, db=fake_db)

    assert creds is not None
    assert creds.token == "new-token"
    assert user.google_access_token == "new-token"
    assert fake_db.committed is True

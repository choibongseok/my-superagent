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
    def __init__(
        self,
        token=None,
        refresh_token=None,
        token_uri=None,
        client_id=None,
        client_secret=None,
        scopes=None,
    ):
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


@pytest.mark.asyncio
async def test_get_user_credentials_validates_required_scopes(monkeypatch):
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
    monkeypatch.setattr(
        google_auth.settings,
        "GOOGLE_SCOPES",
        "scope.read, scope.write",
    )

    creds = await google_auth.get_user_credentials(
        user.id,
        db=fake_db,
        required_scopes=["scope.read", "scope.write"],
    )

    assert creds is not None
    assert creds.scopes == ["scope.read", "scope.write"]


@pytest.mark.asyncio
async def test_get_user_credentials_rejects_missing_required_scopes(monkeypatch):
    user = SimpleNamespace(
        id=uuid4(),
        google_access_token="token",
        google_refresh_token=None,
    )

    class _DB:
        async def execute(self, _):
            return _Result(user)

    monkeypatch.setattr(google_auth, "Credentials", _FakeCreds)
    monkeypatch.setattr(
        google_auth.settings,
        "GOOGLE_SCOPES",
        "scope.read",
    )

    with pytest.raises(ValueError, match="missing required scopes: scope.admin"):
        await google_auth.get_user_credentials(
            user.id,
            db=_DB(),
            required_scopes=["scope.read", "scope.admin"],
        )


@pytest.mark.asyncio
async def test_get_user_credentials_rejects_invalid_user_id():
    with pytest.raises(ValueError, match="user_id must be a valid UUID"):
        await google_auth.get_user_credentials("not-a-uuid", db=object())


def test_get_missing_scopes_normalizes_and_deduplicates_input():
    creds = _FakeCreds(scopes=["scope.read", "scope.write"])

    missing = google_auth.get_missing_scopes(
        creds,
        [" scope.read ", "scope.read", "scope.admin"],
    )

    assert missing == ["scope.admin"]


def test_get_missing_scopes_supports_single_scope_string():
    creds = _FakeCreds(scopes=["scope.read"])

    assert google_auth.get_missing_scopes(creds, "scope.read") == []
    assert google_auth.get_missing_scopes(creds, "scope.admin") == ["scope.admin"]


def test_get_missing_scopes_rejects_invalid_scope_values():
    creds = _FakeCreds(scopes=["scope.read"])

    with pytest.raises(ValueError, match="required_scopes cannot contain empty values"):
        google_auth.get_missing_scopes(creds, ["scope.read", "   "])

    with pytest.raises(TypeError, match="required_scopes must contain only strings"):
        google_auth.get_missing_scopes(creds, ["scope.read", 123])


def test_credentials_have_scopes_returns_true_only_when_all_scopes_exist():
    creds = _FakeCreds(scopes=["scope.read", "scope.write"])

    assert google_auth.credentials_have_scopes(creds, ["scope.read"])
    assert not google_auth.credentials_have_scopes(creds, ["scope.read", "scope.admin"])

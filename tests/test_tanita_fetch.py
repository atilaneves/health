import os
from datetime import datetime, timedelta

import pytest
import requests

from health.tanita import auth, fetch

# Shape of the real login page (fetched 2026-10-14), trimmed.
LOGIN_PAGE = ('<form method="post"  action="/en/user/processlogin" role="form">'
              '<input type="hidden" name="token" value="tok123" required="" id="token">'
              '<input type="text" name="mail" id="mail"><input type="password" name="password" id="password">'
              '<input type="submit" name="login" id="login" value="Login"></form>')
CSV = b"Date,Weight (kg)\n2026-10-14 08:00,72.1\n"


def resp(body, status=200, ctype="text/html"):
    r = requests.Response()
    r.status_code, r._content = status, body if isinstance(body, bytes) else body.encode()
    r.headers["content-type"] = ctype
    return r


class FakeSession(requests.Session):
    def __init__(self, logged_in=False, password="pw"):
        super().__init__()
        self.logged_in, self.password, self.posts, self.gets = logged_in, password, [], []

    def get(self, url, **kw):
        self.gets.append(url)
        if url.endswith(auth.LOGIN_PATH):
            return resp(LOGIN_PAGE)
        return resp(CSV, ctype="text/csv") if self.logged_in else resp(LOGIN_PAGE)

    def post(self, url, data=None, **kw):
        self.posts.append(data)
        self.logged_in = data["password"] == self.password and data["token"] == "tok123"
        return resp("<html>dashboard</html>") if self.logged_in else resp(LOGIN_PAGE)


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(auth, "_password", lambda email: "pw")
    return tmp_path


def test_login_sends_form_token_and_detects_rejection():
    s = FakeSession()
    auth.login_with(s, "me@x", "pw")
    assert s.posts[-1] == {"mail": "me@x", "password": "pw", "token": "tok123", "login": "Login"}
    with pytest.raises(auth.TanitaAuthError, match="rejected"):
        auth.login_with(FakeSession(), "me@x", "wrong")


def test_session_file_has_no_password_and_is_private(state):
    s = FakeSession()
    auth.login_with(s, "me@x", "pw")
    auth.save_session(s, "me@x")
    p = auth.session_file()
    assert "pw" not in p.read_text().replace('"password"', "")
    assert oct(p.stat().st_mode & 0o777) == "0o600" and oct(p.parent.stat().st_mode & 0o777) == "0o700"


def test_get_session_without_login_says_what_to_run(state):
    with pytest.raises(auth.TanitaAuthError, match="health.tanita.auth login"):
        auth.get_session()


def test_relogin_without_keyring_password(state, monkeypatch):
    auth.save_session(FakeSession(), "me@x")
    monkeypatch.setattr(auth, "_password", lambda email: None)
    with pytest.raises(auth.TanitaAuthError, match="no Tanita password"):
        auth.relogin(FakeSession())


def install(monkeypatch, session):
    monkeypatch.setattr(auth, "get_session", lambda: session)


def test_expired_session_relogs_once_and_saves_csv(state, monkeypatch):
    auth.save_session(FakeSession(), "me@x")
    s = FakeSession(logged_in=False)
    install(monkeypatch, s)
    path, network = fetch.fetch(raw=state / "raw")
    assert network and path.read_bytes() == CSV
    assert len(s.posts) == 1


def test_export_from_today_served_from_disk(state, monkeypatch):
    auth.save_session(FakeSession(), "me@x")
    install(monkeypatch, FakeSession(logged_in=True))
    first, _ = fetch.fetch(raw=state / "raw")
    s = FakeSession(logged_in=True)
    install(monkeypatch, s)
    path, network = fetch.fetch(raw=state / "raw")
    assert (path, network) == (first, False) and s.gets == []


def test_stale_unchanged_export_is_not_duplicated(state, monkeypatch):
    auth.save_session(FakeSession(), "me@x")
    install(monkeypatch, FakeSession(logged_in=True))
    first, _ = fetch.fetch(raw=state / "raw")
    old = (datetime.now() - timedelta(days=1)).timestamp()
    os.utime(first, (old, old))
    path, network = fetch.fetch(raw=state / "raw")
    assert network and path == first and len(list((state / "raw").glob("*.csv"))) == 1
    assert first.stat().st_mtime > old


def test_wrong_saved_password_fails_cleanly(state, monkeypatch):
    auth.save_session(FakeSession(), "me@x")
    install(monkeypatch, FakeSession(logged_in=False, password="changed"))
    with pytest.raises(auth.TanitaAuthError, match="rejected"):
        fetch.fetch(raw=state / "raw")

from health import run


class AuthError(Exception):
    pass


def test_auth_error_logs_in_then_retries(capsys):
    calls = []

    def fetch():
        calls.append("fetch")
        if calls.count("fetch") == 1:
            raise AuthError("session expired")

    run._sync("X", fetch, lambda: calls.append("login"), AuthError)
    assert calls == ["fetch", "login", "fetch"]
    assert "X: up to date" in capsys.readouterr().out


def test_other_failures_fall_back_to_cache(capsys):
    def fetch():
        raise ConnectionError("offline")

    logins = []
    run._sync("X", fetch, lambda: logins.append(1), AuthError)
    assert logins == []
    assert "using cached data" in capsys.readouterr().out


def test_failed_login_does_not_abort(capsys):
    def fetch():
        raise AuthError("no session")

    def login():
        raise AuthError("rejected")

    run._sync("X", fetch, login, AuthError)
    assert "not updated" in capsys.readouterr().out

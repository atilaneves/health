from health import prompt


def answers(*xs):
    it = iter(xs)
    return lambda _msg: next(it)


def test_enter_accepts_default():
    assert prompt.ask_email("Tanita", "me@x", input=answers("")) == "me@x"


def test_typed_email_overrides_default():
    assert prompt.ask_email("Tanita", "me@x", input=answers("  other@y ")) == "other@y"


def test_no_default_reprompts_until_answered(monkeypatch):
    monkeypatch.setattr(prompt, "default_email", lambda: None)
    assert prompt.ask_email("Garmin", input=answers("", "me@x")) == "me@x"


def test_env_beats_git(monkeypatch):
    monkeypatch.setenv("HEALTH_EMAIL", "env@x")
    assert prompt.default_email() == "env@x"

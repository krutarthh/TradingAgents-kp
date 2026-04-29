import os

from tradingagents.langsmith_utils import configure_langsmith_from_config


def test_configure_langsmith_forces_on_off(monkeypatch):
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    monkeypatch.delenv("LANGCHAIN_PROJECT", raising=False)
    configure_langsmith_from_config(
        {"langsmith_tracing": True, "langsmith_project": "MyProject"}
    )
    assert os.environ["LANGCHAIN_TRACING_V2"] == "true"
    assert os.environ["LANGCHAIN_PROJECT"] == "MyProject"

    configure_langsmith_from_config({"langsmith_tracing": False})
    assert os.environ["LANGCHAIN_TRACING_V2"] == "false"


def test_configure_langsmith_none_does_not_toggle_tracing(monkeypatch):
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    configure_langsmith_from_config({"langsmith_tracing": None})
    assert os.environ["LANGCHAIN_TRACING_V2"] == "true"

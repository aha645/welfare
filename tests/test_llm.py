"""LLM 공급자 선택과 로컬 클라이언트 동작 테스트 (네트워크/실제 모델 없이 스텁 서버 사용)."""

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from pydantic import BaseModel, Field, JsonValue

from welfare_extract.llm import LocalClient, client_for, load_config


class Answer(BaseModel):
    household: str
    age: int | None


class _SchemaSpec(BaseModel):
    name: str
    strict: bool
    json_schema: dict[str, JsonValue] = Field(alias="schema")


class _ResponseFormat(BaseModel):
    type: str
    json_schema: _SchemaSpec


class _Request(BaseModel):
    """스텁 서버가 받은 요청 본문 (검사에 필요한 필드만)."""

    model: str
    response_format: _ResponseFormat


class _StubState:
    def __init__(self) -> None:
        self.status = 200
        self.content: str | None = '{"household": "독거", "age": 72}'
        self.finish_reason = "stop"
        self.last_body = b""


@pytest.fixture
def stub() -> Iterator[tuple[str, _StubState]]:
    state = _StubState()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers["Content-Length"])
            state.last_body = self.rfile.read(length)
            payload = {"choices": [{"message": {"content": state.content}, "finish_reason": state.finish_reason}]}
            data = json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(state.status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/v1", state
    server.shutdown()


def test_local_client_sends_schema_and_parses(stub: tuple[str, _StubState]) -> None:
    url, state = stub
    result = LocalClient("test-model", url, timeout=5, api_key_env=None).parse("sys", "혼자 살아요", Answer)

    assert result == Answer(household="독거", age=72)
    request = _Request.model_validate_json(state.last_body)
    assert request.model == "test-model"
    assert request.response_format.type == "json_schema"
    assert request.response_format.json_schema.json_schema == Answer.model_json_schema()


def test_local_client_rejects_output_not_matching_schema(stub: tuple[str, _StubState]) -> None:
    url, state = stub
    state.content = '{"household": "독거"}'  # age 누락
    with pytest.raises(ValueError):
        LocalClient("m", url, timeout=5, api_key_env=None).parse("s", "u", Answer)


def test_local_client_reports_truncation(stub: tuple[str, _StubState]) -> None:
    url, state = stub
    state.finish_reason = "length"
    with pytest.raises(RuntimeError, match="잘림"):
        LocalClient("m", url, timeout=5, api_key_env=None).parse("s", "u", Answer)


def test_local_client_reports_http_error(stub: tuple[str, _StubState]) -> None:
    url, state = stub
    state.status = 500
    with pytest.raises(RuntimeError, match="HTTP 500"):
        LocalClient("m", url, timeout=5, api_key_env=None).parse("s", "u", Answer)


CONFIG = """
[providers.claude]
type = "claude"

[providers.local]
type = "local"
model = "qwen2.5:14b"

[tasks]
extraction = "claude"
answer_parsing = "local"
"""


def test_task_routing_and_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    path = tmp_path / "llm.toml"
    path.write_text(CONFIG, encoding="utf-8")

    assert client_for("extraction", path=path).name == "claude:claude-opus-5-5"
    assert client_for("answer_parsing", path=path).name == "local:qwen2.5:14b"
    assert client_for("extraction", override="local", path=path).name == "local:qwen2.5:14b"


def test_unknown_provider_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "llm.toml"
    path.write_text(CONFIG.replace('answer_parsing = "local"', 'answer_parsing = "gpu"'), encoding="utf-8")
    with pytest.raises(ValueError, match="gpu"):
        load_config(path)


def test_project_config_is_valid() -> None:
    config = load_config(Path("config/llm.toml"))
    assert set(config.tasks) == {"extraction", "answer_parsing", "question_wording", "explanation", "verification"}

"""LLM 공급자 선택: Claude API 또는 로컬 모델.

작업(task)마다 어떤 공급자를 쓸지 config/llm.toml 에서 고른다.
두 공급자 모두 같은 pydantic 스키마로 구조화 출력을 받으므로, 호출하는 쪽 코드는 같다.
"""

import os
import tomllib
from pathlib import Path
from typing import Literal, Protocol, TypeVar

import anthropic
import requests
from pydantic import BaseModel, ConfigDict

T = TypeVar("T", bound=BaseModel)

Task = Literal["extraction", "answer_parsing", "question_wording", "explanation", "verification"]
Effort = Literal["low", "medium", "high", "xhigh", "max"]
DEFAULT_CONFIG = Path("config/llm.toml")


class LLMClient(Protocol):
    name: str

    def parse(self, system: str, user: str, schema: type[T]) -> T: ...


class ClaudeClient:
    """Anthropic API. 인증은 ANTHROPIC_API_KEY 또는 `ant auth login` 프로필."""

    def __init__(self, model: str, effort: Effort, max_tokens: int) -> None:
        self.name = f"claude:{model}"
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens
        self.client = anthropic.Anthropic()

    def parse(self, system: str, user: str, schema: type[T]) -> T:
        response = self.client.beta.messages.parse(
            model=self.model,
            max_tokens=self.max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            output_config={"effort": self.effort},
            messages=[{"role": "user", "content": user}],
            output_format=schema,
            # 안전 분류기가 거절하면 서버가 다른 모델로 다시 시도한다
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if response.stop_reason == "refusal":
            raise RuntimeError(f"{self.name}: 모델이 응답을 거절함")
        if response.parsed_output is None:
            raise RuntimeError(f"{self.name}: 구조화 출력 파싱 실패 (stop_reason={response.stop_reason})")
        return response.parsed_output


class _ChatMessage(BaseModel):
    content: str | None = None


class _ChatChoice(BaseModel):
    message: _ChatMessage
    finish_reason: str | None = None


class _ChatCompletion(BaseModel):
    choices: list[_ChatChoice]


class LocalClient:
    """OpenAI 호환 /v1/chat/completions 를 제공하는 로컬 서버 (Ollama, vLLM, llama.cpp server).

    response_format 의 json_schema 로 출력 형식을 강제하고, 받은 JSON을 같은 스키마로 다시 검증한다.
    """

    def __init__(self, model: str, base_url: str, timeout: float, api_key_env: str | None) -> None:
        self.name = f"local:{model}"
        self.model = model
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.timeout = timeout
        self.api_key = os.environ.get(api_key_env, "") if api_key_env else ""

    def parse(self, system: str, user: str, schema: type[T]) -> T:
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": schema.__name__, "schema": schema.model_json_schema(), "strict": True},
            },
            "temperature": 0,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        try:
            res = requests.post(self.url, json=body, headers=headers, timeout=self.timeout)
        except requests.ConnectionError as e:
            raise RuntimeError(f"{self.name}: 로컬 서버({self.url})에 연결할 수 없음. 서버가 실행 중인지 확인하세요.") from e
        if res.status_code != 200:
            raise RuntimeError(f"{self.name}: HTTP {res.status_code} {res.text[:300]}")
        completion = _ChatCompletion.model_validate_json(res.content)
        if not completion.choices or not completion.choices[0].message.content:
            raise RuntimeError(f"{self.name}: 빈 응답")
        choice = completion.choices[0]
        if choice.finish_reason == "length":
            raise RuntimeError(f"{self.name}: 출력이 길이 제한에서 잘림")
        return schema.model_validate_json(choice.message.content or "")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClaudeProvider(_Strict):
    type: Literal["claude"]
    model: str = "claude-opus-5-5"
    effort: Effort = "medium"
    max_tokens: int = 16000

    def build(self) -> LLMClient:
        return ClaudeClient(self.model, self.effort, self.max_tokens)


class LocalProvider(_Strict):
    type: Literal["local"]
    model: str
    base_url: str = "http://localhost:11434/v1"
    timeout: float = 300
    api_key_env: str | None = None

    def build(self) -> LLMClient:
        return LocalClient(self.model, self.base_url, self.timeout, self.api_key_env)


class LLMConfig(_Strict):
    providers: dict[str, ClaudeProvider | LocalProvider]
    tasks: dict[Task, str]


def load_config(path: Path = DEFAULT_CONFIG) -> LLMConfig:
    config = LLMConfig.model_validate(tomllib.loads(path.read_text(encoding="utf-8")))
    unknown = {name for name in config.tasks.values() if name not in config.providers}
    if unknown:
        raise ValueError(f"{path}: tasks 에 정의되지 않은 공급자 {sorted(unknown)}")
    return config


def client_for(task: Task, override: str | None = None, path: Path = DEFAULT_CONFIG) -> LLMClient:
    """작업에 맞는 클라이언트. override 에 공급자 이름을 주면 설정보다 우선한다."""
    config = load_config(path)
    name = override or config.tasks[task]
    if name not in config.providers:
        raise ValueError(f"공급자 '{name}' 없음. 사용 가능: {sorted(config.providers)}")
    return config.providers[name].build()

"""Model providers.

MockProvider is a development double. Evaluation reports label it, and the
release gate refuses to PASS a run that used it.

OpenAI and Anthropic clients are real HTTP integrations. They are not used
by the local demonstration suite.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import httpx
from pydantic import BaseModel, Field

from agentgate.errors import ProviderError


class ChatMessage(BaseModel):
    role: str
    content: str = ""
    tool_calls: List["ToolCallRequest"] = Field(default_factory=list)
    tool_call_id: Optional[str] = None
    name: Optional[str] = None


class ToolCallRequest(BaseModel):
    id: str
    name: str
    arguments: Dict[str, Any]


class ToolSpec(BaseModel):
    name: str
    description: str
    parameters: Dict[str, str]


class ProviderCompletion(BaseModel):
    text: str = ""
    tool_calls: List[ToolCallRequest] = Field(default_factory=list)
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    latency_ms: Optional[float] = None
    model: Optional[str] = None


class ModelProvider:
    name = "base"
    provider_class = "model"
    default_model: Optional[str] = None

    def complete(
        self,
        messages: List[ChatMessage],
        tools: List[ToolSpec],
        model: Optional[str],
    ) -> ProviderCompletion:
        raise NotImplementedError


class MockProvider(ModelProvider):
    """Scripted completions for tests. Not a benchmark and not a release candidate."""

    name = "mock"
    provider_class = "development_double"
    default_model = "mock-scripted"

    def __init__(self, script: List[ProviderCompletion]) -> None:
        self.script = list(script)

    def complete(
        self,
        messages: List[ChatMessage],
        tools: List[ToolSpec],
        model: Optional[str],
    ) -> ProviderCompletion:
        if not self.script:
            raise ProviderError("MockProvider script exhausted")
        return self.script.pop(0)


class OpenAIProvider(ModelProvider):
    name = "openai"
    provider_class = "model"
    default_model = "gpt-4o-mini"

    def __init__(
        self,
        api_key: Optional[str] = None,
        client: Optional[httpx.Client] = None,
        timeout_s: float = 30.0,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get("OPENAI_API_KEY", "")
        self.timeout_s = timeout_s
        self._client = client

    def complete(
        self,
        messages: List[ChatMessage],
        tools: List[ToolSpec],
        model: Optional[str],
    ) -> ProviderCompletion:
        if not self.api_key:
            raise ProviderError("OPENAI_API_KEY is not set")
        chosen = model or self.default_model
        payload = {
            "model": chosen,
            "messages": [_openai_message(message) for message in messages],
            "tools": [_openai_tool(tool) for tool in tools],
        }
        client = self._client or httpx.Client(timeout=self.timeout_s)
        close = self._client is None
        try:
            try:
                response = client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload,
                )
            except httpx.TimeoutException as exc:
                raise ProviderError("OpenAI request timed out") from exc
            except httpx.HTTPError as exc:
                raise ProviderError(f"OpenAI request failed: {exc}") from exc
        finally:
            if close:
                client.close()
        if response.status_code >= 400:
            raise ProviderError(f"OpenAI returned HTTP {response.status_code}")
        body = response.json()
        choice = body["choices"][0]["message"]
        usage = body.get("usage") or {}
        tool_calls = []
        for index, call in enumerate(choice.get("tool_calls") or []):
            import json

            arguments = json.loads(call.get("function", {}).get("arguments") or "{}")
            tool_calls.append(
                ToolCallRequest(
                    id=call.get("id") or f"call-{index}",
                    name=call["function"]["name"],
                    arguments=arguments,
                )
            )
        return ProviderCompletion(
            text=choice.get("content") or "",
            tool_calls=tool_calls,
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            latency_ms=response.elapsed.total_seconds() * 1000 if response.elapsed else None,
            model=chosen,
        )


class AnthropicProvider(ModelProvider):
    name = "anthropic"
    provider_class = "model"
    default_model = "claude-3-5-haiku-latest"

    def __init__(
        self,
        api_key: Optional[str] = None,
        client: Optional[httpx.Client] = None,
        timeout_s: float = 30.0,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get("ANTHROPIC_API_KEY", "")
        self.timeout_s = timeout_s
        self._client = client

    def complete(
        self,
        messages: List[ChatMessage],
        tools: List[ToolSpec],
        model: Optional[str],
    ) -> ProviderCompletion:
        if not self.api_key:
            raise ProviderError("ANTHROPIC_API_KEY is not set")
        chosen = model or self.default_model
        system = "\n".join(message.content for message in messages if message.role == "system")
        converted = []
        for message in messages:
            if message.role == "system":
                continue
            converted.append({"role": "user" if message.role == "tool" else message.role, "content": message.content})
        payload = {
            "model": chosen,
            "max_tokens": 1024,
            "system": system,
            "messages": converted,
            "tools": [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": {"type": "object", "properties": tool.parameters},
                }
                for tool in tools
            ],
        }
        client = self._client or httpx.Client(timeout=self.timeout_s)
        close = self._client is None
        try:
            try:
                response = client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": self.api_key,
                        "anthropic-version": "2023-06-01",
                    },
                    json=payload,
                )
            except httpx.TimeoutException as exc:
                raise ProviderError("Anthropic request timed out") from exc
            except httpx.HTTPError as exc:
                raise ProviderError(f"Anthropic request failed: {exc}") from exc
        finally:
            if close:
                client.close()
        if response.status_code >= 400:
            raise ProviderError(f"Anthropic returned HTTP {response.status_code}")
        body = response.json()
        text_parts = []
        tool_calls = []
        for index, block in enumerate(body.get("content") or []):
            if block.get("type") == "text":
                text_parts.append(block.get("text") or "")
            elif block.get("type") == "tool_use":
                tool_calls.append(
                    ToolCallRequest(
                        id=block.get("id") or f"tool-{index}",
                        name=block.get("name"),
                        arguments=block.get("input") or {},
                    )
                )
        usage = body.get("usage") or {}
        return ProviderCompletion(
            text="\n".join(text_parts),
            tool_calls=tool_calls,
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            latency_ms=response.elapsed.total_seconds() * 1000 if response.elapsed else None,
            model=chosen,
        )


def _openai_message(message: ChatMessage) -> Dict[str, Any]:
    import json

    payload: Dict[str, Any] = {"role": message.role, "content": message.content}
    if message.tool_calls:
        payload["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
            }
            for call in message.tool_calls
        ]
    if message.tool_call_id:
        payload["tool_call_id"] = message.tool_call_id
    return payload


def _openai_tool(tool: ToolSpec) -> Dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": {
                "type": "object",
                "properties": {key: {"type": value} for key, value in tool.parameters.items()},
            },
        },
    }

"""Provider adapters for user-owned OpenAI-compatible, Anthropic and Ollama APIs."""
from collections.abc import AsyncIterator
from typing import Callable

import httpx
from .providers.registry import get_adapter

async def stream_chat(config: dict, messages: list[dict], on_usage: Callable[[int | None, int | None], None] | None = None) -> AsyncIterator[str]:
    adapter = get_adapter(config["protocol"])
    payload = adapter.payload(config, messages, True)
    timeout_seconds = config.get("timeout_seconds", 120)
    timeout = httpx.Timeout(timeout_seconds, connect=min(8, timeout_seconds))
    input_tokens = output_tokens = None
    headers = {**adapter.headers(config), **config.get("headers", {})}
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("POST", adapter.endpoint(config), headers=headers, json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                token, used_in, used_out = adapter.parse_event(line)
                if used_in is not None:
                    input_tokens = used_in
                if used_out is not None:
                    output_tokens = used_out
                if token:
                    yield token
    if on_usage:
        on_usage(input_tokens, output_tokens)


async def complete_chat(config: dict, messages: list[dict]) -> str:
    return "".join([token async for token in stream_chat(config, messages)])


async def test_connection(config: dict) -> str:
    if config["protocol"] != "ollama" and not config.get("api_key"):
        raise ValueError("API Key is required")
    test_config = {**config, "thinking_mode": False, "parameters": {**config.get("parameters", {}), "max_tokens": 8}}
    return await complete_chat(test_config, [
        {"role": "system", "content": "Reply with only OK."},
        {"role": "user", "content": "Connection test."},
    ])

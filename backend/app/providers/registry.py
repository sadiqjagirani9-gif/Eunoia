from .anthropic import AnthropicMessagesAdapter
from .ollama import OllamaAdapter
from .openai_compatible import OpenAICompatibleAdapter

_ADAPTERS = {
    "openai_compatible": OpenAICompatibleAdapter(),
    "anthropic": AnthropicMessagesAdapter(),
    "ollama": OllamaAdapter(),
}


def get_adapter(protocol: str):
    try:
        return _ADAPTERS[protocol]
    except KeyError as exc:
        raise ValueError("不支持的接口协议") from exc

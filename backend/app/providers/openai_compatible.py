import json


class OpenAICompatibleAdapter:
    def endpoint(self, config):
        base = config["base_url"].rstrip("/")
        return base if base.endswith("/chat/completions") else base + "/chat/completions"

    def headers(self, config):
        headers = {"Content-Type": "application/json"}
        if config.get("api_key"):
            headers["Authorization"] = "Bearer " + config["api_key"]
        return headers

    def payload(self, config, messages, stream):
        allowed = {"temperature", "top_p", "max_tokens", "presence_penalty", "frequency_penalty", "seed"}
        options = {key: value for key, value in config.get("parameters", {}).items() if key in allowed and value is not None}
        body = {"model": config["model_id"], "messages": messages, "stream": stream, **options}
        if config.get("thinking_mode"):
            body["reasoning_effort"] = "medium"
        if stream and config.get("capabilities", {}).get("stream_usage"):
            body["stream_options"] = {"include_usage": True}
        return body

    def parse_event(self, line):
        if not line.startswith("data:"):
            return "", None, None
        data = line[5:].strip()
        if data == "[DONE]":
            return "", None, None
        try:
            item = json.loads(data)
            usage = item.get("usage") or {}
            token = item.get("choices", [{}])[0].get("delta", {}).get("content", "") or ""
            return token, usage.get("prompt_tokens"), usage.get("completion_tokens")
        except (ValueError, TypeError, IndexError):
            return "", None, None

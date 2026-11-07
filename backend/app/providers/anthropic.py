import json


class AnthropicMessagesAdapter:
    def endpoint(self, config):
        base = config["base_url"].rstrip("/")
        return base if base.endswith("/v1/messages") else base + "/v1/messages"

    def headers(self, config):
        headers = {"Content-Type": "application/json", "anthropic-version": "2023-06-01"}
        if config.get("api_key"):
            headers["x-api-key"] = config["api_key"]
        return headers

    def payload(self, config, messages, stream):
        options = config.get("parameters", {})
        max_tokens = options.get("max_tokens", 1024)
        system = "\n\n".join(item["content"] for item in messages if item["role"] == "system")
        body = {"model": config["model_id"], "max_tokens": max_tokens,
                "messages": [item for item in messages if item["role"] != "system"], "stream": stream}
        for key in ("temperature", "top_p"):
            if options.get(key) is not None:
                body[key] = options[key]
        if system:
            body["system"] = system
        if config.get("thinking_mode"):
            body["thinking"] = {"type": "enabled", "budget_tokens": min(1024, max(1, max_tokens // 2))}
        return body

    def parse_event(self, line):
        if not line.startswith("data:"):
            return "", None, None
        try:
            item = json.loads(line[5:].strip())
            kind = item.get("type")
            if kind == "content_block_delta":
                return item.get("delta", {}).get("text", ""), None, None
            if kind == "message_start":
                return "", item.get("message", {}).get("usage", {}).get("input_tokens"), None
            if kind == "message_delta":
                return "", None, item.get("usage", {}).get("output_tokens")
        except (ValueError, TypeError):
            pass
        return "", None, None

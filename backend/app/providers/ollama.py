import json


class OllamaAdapter:
    def endpoint(self, config):
        base = config["base_url"].rstrip("/")
        return base if base.endswith("/api/chat") else base + "/api/chat"

    def headers(self, config):
        return {"Content-Type": "application/json"}

    def payload(self, config, messages, stream):
        allowed = {"temperature", "top_p", "presence_penalty", "frequency_penalty", "seed", "num_ctx"}
        options = {key: value for key, value in config.get("parameters", {}).items() if key in allowed and value is not None}
        if config.get("parameters", {}).get("max_tokens") is not None:
            options["num_predict"] = config["parameters"]["max_tokens"]
        payload = {"model": config["model_id"], "messages": messages, "stream": stream, "options": options}
        if config.get("thinking_mode"):
            payload["think"] = True
        return payload

    def parse_event(self, line):
        try:
            item = json.loads(line)
            return item.get("message", {}).get("content", ""), item.get("prompt_eval_count"), item.get("eval_count")
        except (ValueError, TypeError):
            return "", None, None

"""Locally stored, user-owned model configurations and persona assignments."""
import base64
import ipaddress
import ctypes
import json
import os
import uuid
from ctypes import POINTER, Structure, byref, c_void_p, c_uint32, c_wchar_p
from pathlib import Path
from urllib.parse import urlsplit

from cryptography.fernet import Fernet, InvalidToken

from .db import connect, database_path

PERSONAS = ("anatomy", "debate", "guidance", "self_exploration", "lucien", "felix")
PROTOCOLS = {"openai_compatible", "anthropic", "ollama"}
SENSITIVE_HEADERS = {"authorization", "proxy-authorization", "x-api-key", "api-key", "cookie", "set-cookie", "host", "content-length"}


class _Blob(Structure):
    _fields_ = [("cbData", c_uint32), ("pbData", POINTER(ctypes.c_ubyte))]


def _protect_windows(value: bytes, decrypt: bool = False) -> bytes:
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    crypt32.CryptProtectData.argtypes = [POINTER(_Blob), c_wchar_p, c_void_p, c_void_p, c_void_p, c_uint32, POINTER(_Blob)]
    crypt32.CryptProtectData.restype = ctypes.c_int
    crypt32.CryptUnprotectData.argtypes = [POINTER(_Blob), POINTER(c_wchar_p), c_void_p, c_void_p, c_void_p, c_uint32, POINTER(_Blob)]
    crypt32.CryptUnprotectData.restype = ctypes.c_int
    kernel32.LocalFree.argtypes = [c_void_p]
    kernel32.LocalFree.restype = c_void_p
    source_buffer = ctypes.create_string_buffer(value)
    source = _Blob(len(value), ctypes.cast(source_buffer, POINTER(ctypes.c_ubyte)))
    target = _Blob()
    if decrypt:
        description = c_wchar_p()
        ok = crypt32.CryptUnprotectData(byref(source), byref(description), None, None, None, 1, byref(target))
    else:
        ok = crypt32.CryptProtectData(byref(source), "Eunoia local model credentials", None, None, None, 1, byref(target))
    if not ok:
        raise OSError("Windows credential protection failed")
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(target.pbData, c_void_p))


def _fernet() -> Fernet:
    key_path = database_path().parent / ".model-config.key"
    if not key_path.exists():
        key_path.write_bytes(Fernet.generate_key())
        try:
            os.chmod(key_path, 0o600)
        except OSError:
            pass
    return Fernet(key_path.read_bytes())


def encrypt_secret(secret: str) -> str:
    if not secret:
        return ""
    payload = secret.encode("utf-8")
    if os.name == "nt":
        return "dpapi:" + base64.urlsafe_b64encode(_protect_windows(payload)).decode("ascii")
    return "fernet:" + _fernet().encrypt(payload).decode("ascii")


def decrypt_secret(value: str) -> str:
    if not value:
        return ""
    kind, _, payload = value.partition(":")
    try:
        if kind == "dpapi" and os.name == "nt":
            return _protect_windows(base64.urlsafe_b64decode(payload), decrypt=True).decode("utf-8")
        if kind == "fernet":
            return _fernet().decrypt(payload.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, OSError) as exc:
        raise ValueError("无法解密本地 API Key；请重新录入该配置。") from exc
    raise ValueError("本地 API Key 使用了当前系统不支持的加密方式。")


def _public(row) -> dict:
    item = dict(row)
    item.pop("api_key_enc", None)
    item["has_api_key"] = bool(row["api_key_enc"])
    item["parameters"] = json.loads(item.pop("parameters_json") or "{}")
    item["headers"] = json.loads(item.pop("headers_json") or "{}")
    item["capabilities"] = json.loads(item.pop("capabilities_json") or "{}")
    return item


def list_configs() -> list[dict]:
    with connect() as db:
        rows = db.execute("SELECT * FROM model_configs ORDER BY name COLLATE NOCASE").fetchall()
    return [_public(row) for row in rows]


def get_config(config_id: str, include_secret: bool = False) -> dict | None:
    with connect() as db:
        row = db.execute("SELECT * FROM model_configs WHERE id=?", (config_id,)).fetchone()
    if not row:
        return None
    result = _public(row)
    if include_secret:
        result["api_key"] = decrypt_secret(row["api_key_enc"])
    return result


def bindings() -> dict[str, str | None]:
    with connect() as db:
        rows = db.execute("SELECT persona,config_id FROM persona_model_bindings").fetchall()
    return {persona: config_id for persona, config_id in rows}


def assigned_config(persona: str) -> dict | None:
    with connect() as db:
        row = db.execute("SELECT c.* FROM persona_model_bindings b JOIN model_configs c ON c.id=b.config_id WHERE b.persona=? AND c.enabled=1", (persona,)).fetchone()
        if not row:
            default = db.execute("SELECT value FROM settings WHERE key='default_model_config'").fetchone()
            row = db.execute("SELECT * FROM model_configs WHERE id=? AND enabled=1", (default[0],)).fetchone() if default else None
    if not row:
        return None
    result = _public(row)
    result["api_key"] = decrypt_secret(row["api_key_enc"])
    return result


def save_config(data: dict, config_id: str | None = None) -> dict:
    protocol = data["protocol"]
    if protocol not in PROTOCOLS:
        raise ValueError("不支持的接口协议")
    base_url = data["base_url"].strip().rstrip("/")
    parsed_url = urlsplit(base_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname or parsed_url.username or parsed_url.password or parsed_url.query or parsed_url.fragment:
        raise ValueError("API Base URL 必须以 http:// 或 https:// 开头")
    host = parsed_url.hostname.lower()
    local_host = host == "localhost"
    try:
        local_host = local_host or ipaddress.ip_address(host).is_loopback
    except ValueError:
        pass
    if parsed_url.scheme != "https" and not local_host:
        raise ValueError("远程 API 必须使用 HTTPS；HTTP 仅允许回环本地地址")
    timeout = float(data.get("timeout_seconds", 120))
    if timeout < 2 or timeout > 300:
        raise ValueError("超时时间须为 2 到 300 秒")
    headers = data.get("headers", {})
    if not isinstance(headers, dict) or len(headers) > 20:
        raise ValueError("自定义请求头格式无效或数量过多")
    for name, value in headers.items():
        if str(name).lower().strip() in SENSITIVE_HEADERS or "\r" in str(name) + str(value) or "\n" in str(name) + str(value):
            raise ValueError("自定义请求头不能包含认证、Cookie、Host 等敏感字段或换行符")
    capabilities = data.get("capabilities", {})
    if not isinstance(capabilities, dict):
        raise ValueError("模型能力必须是对象")
    for price in (data.get("input_price_per_million"), data.get("output_price_per_million")):
        if price is not None and float(price) < 0:
            raise ValueError("模型价格不能为负数")
    if protocol == "ollama" and not data["model_id"].strip():
        raise ValueError("请填写 Ollama 模型 ID")
    if protocol != "ollama" and not (data.get("api_key") or (config_id and not data.get("clear_api_key") and _stored_key_exists(config_id))):
        raise ValueError("远程 API 配置必须填写 API Key")
    config_id = config_id or str(uuid.uuid4())
    with connect() as db:
        old = db.execute("SELECT api_key_enc FROM model_configs WHERE id=?", (config_id,)).fetchone()
        secret = data.get("api_key", "")
        if secret:
            secret = encrypt_secret(secret)
        elif old:
            secret = old["api_key_enc"] if not data.get("clear_api_key") else ""
        else:
            secret = ""
        parameters = json.dumps(data.get("parameters", {}), ensure_ascii=False)
        db.execute("""INSERT INTO model_configs(id,name,provider,base_url,model_id,protocol,api_key_enc,parameters_json,headers_json,timeout_seconds,capabilities_json,input_price_per_million,output_price_per_million,enabled)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,1) ON CONFLICT(id) DO UPDATE SET name=excluded.name,provider=excluded.provider,
        base_url=excluded.base_url,model_id=excluded.model_id,protocol=excluded.protocol,
        api_key_enc=excluded.api_key_enc,parameters_json=excluded.parameters_json,headers_json=excluded.headers_json,timeout_seconds=excluded.timeout_seconds,capabilities_json=excluded.capabilities_json,input_price_per_million=excluded.input_price_per_million,output_price_per_million=excluded.output_price_per_million,enabled=1,updated_at=CURRENT_TIMESTAMP""",
                   (config_id, data["name"].strip(), data.get("provider", "custom").strip() or "custom", base_url,
                    data["model_id"].strip(), protocol, secret, parameters,
                    json.dumps(headers, ensure_ascii=False), timeout, json.dumps(capabilities, ensure_ascii=False),
                    data.get("input_price_per_million"), data.get("output_price_per_million")))
    return get_config(config_id)


def _stored_key_exists(config_id: str) -> bool:
    with connect() as db:
        row = db.execute("SELECT api_key_enc FROM model_configs WHERE id=?", (config_id,)).fetchone()
    return bool(row and row["api_key_enc"])


def assign(persona: str, config_id: str | None) -> None:
    if persona not in PERSONAS:
        raise ValueError("人格空间无效")
    with connect() as db:
        if config_id and not db.execute("SELECT 1 FROM model_configs WHERE id=? AND enabled=1", (config_id,)).fetchone():
            raise ValueError("模型配置不存在")
        db.execute("INSERT INTO persona_model_bindings(persona,config_id) VALUES(?,?) ON CONFLICT(persona) DO UPDATE SET config_id=excluded.config_id,updated_at=CURRENT_TIMESTAMP", (persona, config_id))


def delete_config(config_id: str) -> bool:
    with connect() as db:
        db.execute("DELETE FROM settings WHERE key='default_model_config' AND value=?", (config_id,))
        cursor = db.execute("DELETE FROM model_configs WHERE id=?", (config_id,))
    return bool(cursor.rowcount)


def resolve(persona: str) -> dict | None:
    if persona not in PERSONAS:
        return None
    config = assigned_config(persona)
    if not config:
        return None
    settings = persona_settings().get(persona, {})
    parameters = dict(config.get("parameters", {}))
    if settings.get("temperature") is not None:
        parameters["temperature"] = settings["temperature"]
    if settings.get("max_output_tokens") is not None:
        parameters["max_tokens"] = settings["max_output_tokens"]
    config["parameters"] = parameters
    config["thinking_mode"] = bool(settings.get("thinking_mode") and config.get("capabilities", {}).get("thinking_mode"))
    return config


def get_default() -> str | None:
    with connect() as db:
        row = db.execute("SELECT value FROM settings WHERE key='default_model_config'").fetchone()
    return row[0] if row else None


def set_default(config_id: str | None) -> None:
    with connect() as db:
        if config_id and not db.execute("SELECT 1 FROM model_configs WHERE id=? AND enabled=1", (config_id,)).fetchone():
            raise ValueError("默认模型配置不存在")
        if config_id:
            db.execute("INSERT INTO settings(key,value) VALUES('default_model_config',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (config_id,))
        else:
            db.execute("DELETE FROM settings WHERE key='default_model_config'")


def set_persona_settings(persona: str, temperature: float | None, max_output_tokens: int | None, thinking_mode: bool) -> dict:
    if persona not in PERSONAS:
        raise ValueError("人格空间无效")
    if temperature is not None and not 0 <= temperature <= 2:
        raise ValueError("Temperature 必须在 0 到 2 之间")
    if max_output_tokens is not None and not 1 <= max_output_tokens <= 200000:
        raise ValueError("最大输出 Token 设置无效")
    with connect() as db:
        db.execute("INSERT INTO persona_model_settings(persona,temperature,max_output_tokens,thinking_mode) VALUES(?,?,?,?) ON CONFLICT(persona) DO UPDATE SET temperature=excluded.temperature,max_output_tokens=excluded.max_output_tokens,thinking_mode=excluded.thinking_mode,updated_at=CURRENT_TIMESTAMP", (persona, temperature, max_output_tokens, int(thinking_mode)))
        row = db.execute("SELECT * FROM persona_model_settings WHERE persona=?", (persona,)).fetchone()
    result = dict(row)
    result["thinking_mode"] = bool(result["thinking_mode"])
    return result


def persona_settings() -> dict[str, dict]:
    with connect() as db:
        rows = db.execute("SELECT * FROM persona_model_settings").fetchall()
    return {row["persona"]: {**dict(row), "thinking_mode": bool(row["thinking_mode"])} for row in rows}


def record_usage(config: dict, persona: str, status: str, input_tokens: int | None = None, output_tokens: int | None = None, error_category: str | None = None) -> None:
    price_in, price_out = config.get("input_price_per_million"), config.get("output_price_per_million")
    estimate = ((input_tokens * price_in + output_tokens * price_out) / 1_000_000
                if input_tokens is not None and output_tokens is not None and price_in is not None and price_out is not None else None)
    with connect() as db:
        db.execute("INSERT INTO model_usage(config_id,persona,provider,model_id,input_tokens,output_tokens,cost_estimate,cost_basis,status,error_category) VALUES(?,?,?,?,?,?,?,?,?,?)", (config["id"], persona, config["provider"], config["model_id"], input_tokens, output_tokens, estimate, "user_rate_estimate" if estimate is not None else "unknown", status, error_category))


def usage_summary() -> dict:
    with connect() as db:
        recent = [dict(row) for row in db.execute("SELECT * FROM model_usage ORDER BY id DESC LIMIT 100").fetchall()]
        daily = [dict(row) for row in db.execute("SELECT date(created_at) day,persona,SUM(input_tokens) input_tokens,SUM(output_tokens) output_tokens,SUM(cost_estimate) estimated_cost,COUNT(*) calls FROM model_usage WHERE created_at>=date('now','-29 days') GROUP BY day,persona ORDER BY day DESC,persona").fetchall()]
        monthly = [dict(row) for row in db.execute("SELECT strftime('%Y-%m',created_at) month,persona,SUM(input_tokens) input_tokens,SUM(output_tokens) output_tokens,SUM(cost_estimate) estimated_cost,COUNT(*) calls FROM model_usage WHERE created_at>=date('now','-12 months') GROUP BY month,persona ORDER BY month DESC,persona").fetchall()]
    return {"recent": recent, "daily": daily, "monthly": monthly}

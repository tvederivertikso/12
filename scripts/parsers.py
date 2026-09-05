"""Parse common proxy subscription links and build single-node Xray configs."""
from __future__ import annotations

import base64
import json
import urllib.parse
from typing import Any

SUPPORTED = ("vmess://", "vless://", "trojan://", "ss://")


def _b64decode(value: str) -> str:
    value = value.strip()
    value += "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value.encode()).decode("utf-8", "replace")


def expand_subscription(text: str) -> list[str]:
    """Return individual supported URI lines from plain or base64 text."""
    text = text.strip()
    candidates = [line.strip() for line in text.splitlines() if line.strip()]
    if any(line.lower().startswith(SUPPORTED) for line in candidates):
        return [line for line in candidates if line.lower().startswith(SUPPORTED)]
    try:
        decoded = _b64decode("".join(candidates))
    except Exception:
        return []
    return [line.strip() for line in decoded.splitlines()
            if line.strip().lower().startswith(SUPPORTED)]


def _query(uri: str) -> tuple[urllib.parse.ParseResult, dict[str, str]]:
    parsed = urllib.parse.urlparse(uri)
    return parsed, {k: v[-1] for k, v in urllib.parse.parse_qs(parsed.query).items()}


def _stream(q: dict[str, str], security: str | None = None) -> dict[str, Any]:
    network = q.get("type", q.get("network", "tcp"))
    security = security or q.get("security")
    result: dict[str, Any] = {"network": network}
    if security:
        result["security"] = security
    if network == "ws":
        result["wsSettings"] = {"path": q.get("path", "/"), "headers": {"Host": q.get("host", "")}}
    elif network == "grpc":
        result["grpcSettings"] = {"serviceName": q.get("serviceName", "")}
    elif network == "httpupgrade":
        result["httpupgradeSettings"] = {"path": q.get("path", "/"), "host": q.get("host", "")}
    if security == "tls":
        result["tlsSettings"] = {"serverName": q.get("sni", q.get("host", "")), "allowInsecure": q.get("allowInsecure", "false").lower() == "true"}
    elif security == "reality":
        reality: dict[str, Any] = {"show": False, "fingerprint": q.get("fp", "chrome"), "serverName": q.get("sni", q.get("host", ""))}
        if q.get("pbk"):
            reality["publicKey"] = q["pbk"]
        if q.get("sid"):
            reality["shortId"] = q["sid"]
        result["realitySettings"] = reality
    return result


def to_xray(uri: str) -> dict[str, Any] | None:
    """Convert one URI to an Xray outbound object, or None if unsupported."""
    parsed, q = _query(uri)
    scheme = parsed.scheme.lower()

    if scheme == "vmess":
        try:
            data = json.loads(_b64decode(uri[8:].split("#", 1)[0]))
        except Exception:
            return None
        host = data.get("add")
        port = int(data.get("port", 0))
        user = {"id": data.get("id", ""), "alterId": int(data.get("aid", 0)), "security": data.get("scy", "auto")}
        stream = _stream({"type": data.get("net", "tcp"), "host": data.get("host", ""), "path": data.get("path", "/")}, data.get("tls") or None)
        if data.get("tls") == "tls":
            stream["tlsSettings"] = {"serverName": data.get("sni", data.get("host", host)), "allowInsecure": True}
        name = urllib.parse.unquote(parsed.fragment) or f"vmess://{host}:{port}"
        return {"protocol": "vmess", "settings": {"vnext": [{"address": host, "port": port, "users": [user]}]}, "streamSettings": stream, "tag": name}

    try:
        host = parsed.hostname
        port = parsed.port
    except ValueError:
        return None
    if not host or not port:
        return None
    name = urllib.parse.unquote(parsed.fragment) or f"{scheme}://{host}:{port}"

    if scheme == "vless":
        user: dict[str, Any] = {"id": urllib.parse.unquote(parsed.username or ""), "encryption": q.get("encryption", "none")}
        if q.get("flow"):
            user["flow"] = q["flow"]
        return {"protocol": "vless", "settings": {"vnext": [{"address": host, "port": port, "users": [user]}]}, "streamSettings": _stream(q), "tag": name}

    if scheme == "trojan":
        return {"protocol": "trojan", "settings": {"servers": [{"address": host, "port": port, "password": urllib.parse.unquote(parsed.username or "")} ]}, "streamSettings": _stream(q, q.get("security", "tls")), "tag": name}

    if scheme == "ss":
        userinfo = urllib.parse.unquote(parsed.username or "")
        if not userinfo and parsed.netloc:
            try:
                userinfo = _b64decode(parsed.netloc.split("@", 1)[0])
            except Exception:
                pass
        if ":" not in userinfo:
            return None
        method, password = userinfo.split(":", 1)
        return {"protocol": "shadowsocks", "settings": {"servers": [{"address": host, "port": port, "method": method, "password": password}]}, "tag": name}
    return None


def dedupe(uris: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for uri in uris:
        key = uri.split("#", 1)[0]
        if key not in seen and to_xray(uri):
            seen.add(key)
            result.append(uri)
    return result

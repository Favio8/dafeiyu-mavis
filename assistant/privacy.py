"""Central storage redaction; credential values never enter the task API."""
import re

_KEY = re.compile(r"sk-[A-Za-z0-9_-]{6,}")
_ASSIGNED = re.compile(r"(?i)(api[_ -]?key|authorization|password|token)\s*[:=]\s*\S+")
_BEARER = re.compile(r"(?i)\bBearer\s+\S+")
_CHINESE_SECRET = re.compile(r"(密码|验证码|密钥)\s*[:：=]?\s*\S+")


def redact(text: str) -> str:
    """Remove recognizable credentials from text before any persistence or UI event."""
    return _CHINESE_SECRET.sub(r"\1=[REDACTED]", _BEARER.sub("Bearer [REDACTED]", _ASSIGNED.sub(r"\1=[REDACTED]", _KEY.sub("[REDACTED]", text))))

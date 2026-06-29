"""Heuristic log parser.

Extracts the salient signal (error message + stack trace + service hints) from
a raw log line. This is intentionally dependency-free and fast; the heavy
semantic understanding happens in the embedding + LLM layers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Patterns describing "interesting" log lines. Order matters.
_EXCEPTION_RE = re.compile(
    r"(?P<exc>(?:[A-Z][\w$]*(?:Error|Exception))"
    r"|Traceback|Panic|Fatal|OOM|OutOfMemory|"
    r"ConnectionRefused|Deadlock|SEGFAULT)"
)
# Java/Python style stack frames: "at foo.bar.Baz.method(File.java:12)"
_STACK_FRAME_RE = re.compile(
    r"^\s*(at\s+[\w$.<>]+\([^)]*\)|File\s+\"[^\"]+\",\s+line\s+\d+.*|"
    r"\s+at\s+.+:\d+)"
)
# Common key=value metadata ("service=payments", "ip=10.0.0.1").
_KV_RE = re.compile(r"\b(?P<key>[\w.-]+)=(?P<val>[^\s,]+)")
# An IPv4 address.
_IPV4_RE = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
# A typical log level token.
_LEVEL_RE = re.compile(r"\b(ERROR|ERR|FATAL|CRITICAL|WARN(?:ING)?|PANIC)\b")


@dataclass(slots=True)
class LogExtraction:
    error_message: str
    stack_trace: str | None
    service: str | None
    server_ip: str | None
    exception_type: str | None
    severity: str
    # A normalized blob best suited for embedding & retrieval.
    canonical_text: str


def _extract_stack_trace(text: str) -> str | None:
    frames = [line.strip() for line in text.splitlines() if _STACK_FRAME_RE.match(line)]
    return "\n".join(frames) if frames else None


def _extract_exception_type(text: str) -> str | None:
    m = _EXCEPTION_RE.search(text)
    return m.group("exc") if m else None


def _extract_kv(text: str) -> dict[str, str]:
    return {m.group("key"): m.group("val") for m in _KV_RE.finditer(text)}


def parse_log(raw: str) -> LogExtraction:
    """Parse a raw log string into structured fields."""
    text = raw.strip()
    kv = _extract_kv(text)

    exc_type = _extract_exception_type(text)
    stack = _extract_stack_trace(text)

    # The "message" is the first non-stack, non-empty, non-trivial line.
    msg_lines = [
        ln.strip() for ln in text.splitlines() if ln.strip() and not _STACK_FRAME_RE.match(ln)
    ]
    error_message = msg_lines[0] if msg_lines else text[:280]

    service = kv.get("service") or kv.get("app") or kv.get("module")
    ip_match = _IPV4_RE.search(text)
    # Prefer an actual IPv4 (e.g. embedded in a URL) over a hostname label.
    server_ip = kv.get("ip") or (ip_match.group(0) if ip_match else None) or kv.get("host")

    level_match = _LEVEL_RE.search(text)
    severity = level_match.group(1).upper() if level_match else "ERROR"

    # Canonical text emphasizes the exception type + first message line, which
    # gives the local embedding the most discriminative signal.
    canonical_parts = [p for p in [exc_type, error_message] if p]
    canonical_text = " | ".join(canonical_parts) or text[:280]

    return LogExtraction(
        error_message=error_message[:512],
        stack_trace=stack,
        service=service,
        server_ip=server_ip,
        exception_type=exc_type,
        severity=severity,
        canonical_text=canonical_text,
    )

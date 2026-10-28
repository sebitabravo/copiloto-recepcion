"""Métricas del prototipo calculadas exclusivamente desde los eventos del rango."""

import json
import math
import sqlite3
from collections.abc import Mapping
from statistics import median

from copiloto import events


def compute_metrics(conn: sqlite3.Connection, start: float, end: float, config) -> dict:
    """Calcula indicadores sobre el intervalo UTC semiabierto [start, end)."""
    rows = events.events_between(conn, start, end)
    counts = dict.fromkeys(sorted(events.EVENT_KINDS), 0)
    starts = {}
    replies = {}
    bookings = {}
    complete_captures = set()
    latencies = []
    queries = 0
    ai_latencies, ai_tools, ai_tokens = [], {}, 0

    for row in rows:
        kind = row["kind"]
        conversation_id = row["conversation_id"]
        payload = json.loads(row["payload"])
        counts[kind] = counts.get(kind, 0) + 1
        if kind == "commercial_started":
            starts.setdefault(conversation_id, (row["ts"], payload.get("in_shift")))
        elif kind == "human_first_reply":
            replies.setdefault(conversation_id, []).append(row["ts"])
        elif kind == "booking_confirmed":
            bookings.setdefault(conversation_id, []).append(row["ts"])
        elif kind == "night_capture" and payload.get("complete") is True:
            complete_captures.add(conversation_id)
        elif kind == "faq_answered":
            latencies.append(row["ts"] - payload["inbound_ts"])
        elif kind == "inbound" and payload.get("greeting") is False:
            queries += 1
        elif kind == "ai_reply":
            ai_latencies.append(payload.get("latency_ms", 0) / 1000)
            ai_tokens += payload.get("tokens") or 0
            for tool in payload.get("tools", []):
                ai_tools[tool] = ai_tools.get(tool, 0) + 1

    def config_value(name, default):
        if isinstance(config, Mapping):
            return config.get(name, default)
        return getattr(config, name, default)

    sla_s = config_value("sla_red_s", 180)
    in_shift = 0
    compliant = 0
    converted = 0
    night_conversations = set()
    for conversation_id, (started_at, shift) in starts.items():
        if shift is True:
            in_shift += 1
            # Una respuesta anterior al inicio no satisface este compromiso comercial.
            first_reply = next((ts for ts in replies.get(conversation_id, []) if ts >= started_at), None)
            if first_reply is not None and first_reply - started_at < sla_s:
                compliant += 1
        elif shift is False:
            night_conversations.add(conversation_id)
        if any(0 <= ts - started_at <= 604800 for ts in bookings.get(conversation_id, [])):
            converted += 1

    def percentage(numerator, denominator):
        return 100 * numerator / denominator if denominator else None

    fixed_monthly_clp = config_value("fixed_monthly_clp", 90000)
    usage_m_clp = config_value("usage_m_clp", 0)
    latencies.sort()
    return {
        "faq_latency_median_s": median(latencies) if latencies else None,
        "faq_latency_p95_s": latencies[math.ceil(0.95 * len(latencies)) - 1] if latencies else None,
        "commercial_response_compliance_pct": percentage(compliant, in_shift),
        "commercial_started_in_shift": in_shift,
        "commercial_answered_within_180": compliant,
        "night_capture_rate_pct": percentage(len(complete_captures & night_conversations), len(night_conversations)),
        "direct_conversion_pct": percentage(converted, len(starts)),
        "queries": queries,
        "cost_per_query_clp": (fixed_monthly_clp + usage_m_clp) / queries if queries else None,
        "fixed_monthly_clp": fixed_monthly_clp,
        "usage_m_clp": usage_m_clp,
        "ai_replies": counts["ai_reply"],
        "ai_latency_median_s": median(ai_latencies) if ai_latencies else None,
        "ai_bookings": counts["ai_booking"],
        "ai_guardrail_hits": counts["ai_guardrail"],
        "ai_tokens": ai_tokens,
        "ai_tools": ai_tools,
        "counts": counts,
        "range": {"start": start, "end": end},
    }

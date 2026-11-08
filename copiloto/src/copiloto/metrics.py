"""Métricas del prototipo calculadas exclusivamente desde los eventos del rango.

Metas (EVA2): FAQ en menos de 10 s; primera respuesta humana PERTINENTE en menos de 180 s para las consultas
que entraron en turno, medida por solicitud desde que entró la consulta comercial.
"""

import json
import math
import sqlite3
from collections.abc import Mapping
from statistics import median

from copiloto import events

SCOPES = {"demo": events.DEMO, "operation": events.OPERATION}

HISTORICAL_RULE = (
    "Eventos anteriores a la medición por solicitud (sin request_id) se miden por conversación, como antes; "
    "eventos sin origen registrado cuentan como operación si la conversación tiene id positivo (Chatwoot) y como "
    "demo si es 0; con id negativo no se puede saber (demo o seudónimo de retención) y quedan fuera."
)


def _event_scope(row) -> str | None:
    """Origen del evento; para los históricos sin columna `source`, la mejor evidencia disponible."""
    if row["source"]:
        return row["source"]
    if row["conversation_id"] > 0:
        return events.OPERATION
    if row["conversation_id"] == 0:
        return events.DEMO
    return None


def compute_metrics(
    conn: sqlite3.Connection, start: float, end: float, config, scope: str | None = None,
    conversation_ids: set[int] | None = None,
) -> dict:
    """Calcula indicadores sobre el intervalo UTC semiabierto [start, end).

    `scope`: "demo", "operation" o None (todo, para compatibilidad). La primera respuesta humana se mide por
    SOLICITUD y solo para consultas que entraron en turno; tomar la solicitud y acusar recibo se informan aparte
    y nunca cuentan como respuesta. `conversation_ids` limita a esas conversaciones (la corrida de una demo).
    """
    wanted = SCOPES.get(scope) if scope is not None else None
    if scope is not None and wanted is None:
        raise ValueError("scope debe ser demo, operation o None")
    rows = events.events_between(conn, start, end)
    counts = dict.fromkeys(sorted(events.EVENT_KINDS), 0)
    starts = {}
    replies = {}
    bookings = {}
    complete_captures = set()
    latencies = []
    queries = 0
    ai_latencies, ai_tools, ai_tokens = [], {}, 0
    legacy_requests = set()
    unknown_source = 0

    def request_key(conversation_id: int, payload: dict) -> tuple:
        request_id = payload.get("request_id")
        return ("request", request_id) if isinstance(request_id, int) else ("conversation", conversation_id)

    for row in rows:
        if conversation_ids is not None and row["conversation_id"] not in conversation_ids:
            continue
        origin = _event_scope(row)
        if origin is None:
            unknown_source += 1
            if wanted is not None:
                continue
        elif wanted is not None and origin != wanted:
            continue
        kind = row["kind"]
        conversation_id = row["conversation_id"]
        payload = json.loads(row["payload"])
        counts[kind] = counts.get(kind, 0) + 1
        if kind == "commercial_started":
            key = request_key(conversation_id, payload)
            if key[0] == "conversation":
                legacy_requests.add(key)
            # El reloj parte cuando entró la consulta comercial; eventos antiguos sin ese dato usan el traspaso.
            starts.setdefault(key, (payload.get("inbound_ts", row["ts"]), payload.get("in_shift"), conversation_id))
        elif kind == "human_first_reply":
            replies.setdefault(request_key(conversation_id, payload), []).append(row["ts"])
        elif kind == "booking_confirmed":
            bookings.setdefault(conversation_id, []).append(row["ts"])
        elif kind == "night_capture" and payload.get("complete") is True:
            complete_captures.add(request_key(conversation_id, payload))
        elif kind == "faq_answered":
            latencies.append(row["ts"] - payload["inbound_ts"])
        elif kind == "inbound" and payload.get("greeting") is False:
            queries += 1
        elif kind == "ai_reply":
            if payload.get("outcome") != "fallback":
                ai_latencies.append(payload.get("latency_ms", 0) / 1000)
            ai_tokens += payload.get("tokens") or 0
            for tool in payload.get("tools", []):
                ai_tools[tool] = ai_tools.get(tool, 0) + 1

    def config_value(name, default):
        if isinstance(config, Mapping):
            return config.get(name, default)
        return getattr(config, name, default)

    sla_s = config_value("sla_red_s", 180)
    faq_target_s = config_value("faq_target_s", 10)
    in_shift = 0
    compliant = 0
    converted = 0
    first_reply_times = []
    night_requests = set()
    for key, (started_at, shift, conversation_id) in starts.items():
        if shift is True:
            in_shift += 1
            # Una respuesta anterior al inicio no satisface este compromiso comercial.
            first_reply = next((ts for ts in sorted(replies.get(key, [])) if ts >= started_at), None)
            if first_reply is not None:
                first_reply_times.append(first_reply - started_at)
                if first_reply - started_at < sla_s:
                    compliant += 1
        elif shift is False:
            night_requests.add(key)
        if any(0 <= ts - started_at <= 604800 for ts in bookings.get(conversation_id, [])):
            converted += 1

    def percentage(numerator, denominator):
        return 100 * numerator / denominator if denominator else None

    fixed_monthly_clp = config_value("fixed_monthly_clp", 90000)
    usage_m_clp = config_value("usage_m_clp", 0)
    latencies.sort()
    return {
        "scope": scope or "all",
        "faq_latency_median_s": median(latencies) if latencies else None,
        "faq_latency_p95_s": latencies[math.ceil(0.95 * len(latencies)) - 1] if latencies else None,
        "faq_target_s": faq_target_s,
        "faq_within_target_pct": percentage(sum(1 for value in latencies if value < faq_target_s), len(latencies)),
        "commercial_response_compliance_pct": percentage(compliant, in_shift),
        "commercial_started_in_shift": in_shift,
        "commercial_started_out_of_shift": len(night_requests),
        "first_reply_median_s": median(first_reply_times) if first_reply_times else None,
        # Tomar y acusar recibo son pasos distintos de la respuesta pertinente: se informan, no cuentan.
        "requests_taken": counts["request_taken"],
        "acks": counts["human_ack"],
        # La clave sigue al umbral configurado; con 180 s emite la clave histórica exacta.
        f"commercial_answered_within_{sla_s}": compliant,
        # Alias de compatibilidad: los paneles históricos leen el valor con el umbral original de 180 s.
        **({} if sla_s == 180 else {"commercial_answered_within_180": compliant}),
        "night_capture_rate_pct": percentage(len(complete_captures & night_requests), len(night_requests)),
        "direct_conversion_pct": percentage(converted, len(starts)),
        "queries": queries,
        "cost_per_query_clp": (fixed_monthly_clp + usage_m_clp) / queries if queries else None,
        "fixed_monthly_clp": fixed_monthly_clp,
        "usage_m_clp": usage_m_clp,
        "ai_replies": counts["ai_reply"],
        "ai_fallbacks": counts["ai_fallback"],
        # Turnos de IA (respondidos o degradados) que terminaron en el menú guiado.
        "ai_fallback_rate_pct": percentage(counts["ai_fallback"], counts["ai_reply"]),
        "ai_latency_median_s": median(ai_latencies) if ai_latencies else None,
        "ai_bookings": counts["ai_booking"],
        "ai_guardrail_hits": counts["ai_guardrail"],
        "ai_tokens": ai_tokens,
        "ai_tools": ai_tools,
        "counts": counts,
        "historical_incomplete": {
            "requests_without_id": len(legacy_requests),
            "events_without_source": unknown_source,
            "rule": HISTORICAL_RULE,
        },
        "range": {"start": start, "end": end},
    }

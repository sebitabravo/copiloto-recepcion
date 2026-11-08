#!/usr/bin/env python3
"""Informe del piloto: lee las métricas del copiloto y las compara con las metas acordadas.

Uso:
    python scripts/pilot_report.py --days 14
    PANEL_TOKEN=... python scripts/pilot_report.py --days 14 --csv piloto.csv

/metricas exige sesión del panel: el token sale de PANEL_TOKEN del entorno; si falta, se abre una
sesión de demo (POST /api/demo/session, requiere DEMO_ENABLED) y se reutiliza su cookie firmada.

Las metas salen de la Unidad 2: FAQ bajo 10 s, primera respuesta comercial humana bajo 180 s en
al menos 90 % de las consultas del turno, y captura nocturna informada aparte.
"""

import argparse
import csv
import http.cookiejar
import json
import os
import sys
import urllib.error
import urllib.request

FAQ_TARGET_S = 10.0
COMPLIANCE_TARGET_PCT = 90.0

# Windows con consola cp1252: los símbolos (≥, —) del informe no caben en el codec local.
reconfigure = getattr(sys.stdout, "reconfigure", None)
if callable(reconfigure):
    reconfigure(encoding="utf-8")


# La cookie de la sesión de demo es HttpOnly y firmada: el jar la guarda y la reenvía por host.
OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def fetch(path: str, token: str | None = None) -> dict:
    headers = {"X-Panel-Token": token} if token else {}
    request = urllib.request.Request(path, headers=headers)
    with OPENER.open(request, timeout=15) as response:
        return json.load(response)


def open_demo_session(base: str) -> None:
    """Sin PANEL_TOKEN, el modo demo local entrega la cookie firmada que /metricas acepta."""
    request = urllib.request.Request(f"{base}/api/demo/session", data=b"", method="POST")
    with OPENER.open(request, timeout=15):
        return None


def panel_token() -> str:
    """PANEL_TOKEN del entorno; si falta, main abre una sesión de demo y usa su cookie."""
    return (os.environ.get("PANEL_TOKEN") or "").strip()


def status(ok: bool | None) -> str:
    if ok is None:
        return "—"
    return "cumple" if ok else "no cumple"


def main() -> int:
    parser = argparse.ArgumentParser(description="Informe del piloto del copiloto de recepción.")
    parser.add_argument("--days", type=int, default=14, help="ventana del piloto en días")
    parser.add_argument("--csv", help="ruta para exportar los números crudos")
    args = parser.parse_args()

    base = os.environ.get("COPILOTO_URL", "http://localhost:8100").rstrip("/")
    token = panel_token()

    if not token:
        try:
            open_demo_session(base)
        except (urllib.error.URLError, OSError) as error:
            print(
                "No pude obtener acceso a /metricas. Ese panel exige sesión: define PANEL_TOKEN en el "
                "entorno, o habilita el modo demo (DEMO_ENABLED=1 y el stack levantado) para que "
                f"POST {base}/api/demo/session entregue la cookie. Detalle: {type(error).__name__}",
                flush=True,
            )
            return 2

    try:
        metrics = fetch(f"{base}/metricas/data.json?days={args.days}", token)
    except (urllib.error.URLError, ValueError) as error:
        print(
            f"No pude leer las métricas en {base}: /metricas requiere PANEL_TOKEN o la cookie de demo. "
            f"Detalle: {error}",
            flush=True,
        )
        return 2

    shift = {}
    if token:
        try:
            # El resumen del turno acepta hasta 72 h; para ventanas mayores se informa ese tope.
            shift = fetch(f"{base}/api/panel/shift?hours={min(args.days * 24, 72)}", token)
        except (urllib.error.URLError, ValueError):
            print("Aviso: no pude leer el resumen del turno; el informe sigue sin esa sección.")

    def value(key):
        return metrics.get(key)

    def fmt(number, unit: str, digits: int = 1) -> str:
        if number is None:
            return "—"
        return f"{round(float(number), digits):g} {unit}".strip()

    faq_median = value("faq_latency_median_s")
    compliance_pct = value("commercial_response_compliance_pct")

    rows = [
        (
            "Latencia FAQ (mediana)",
            fmt(faq_median, "s", 2),
            f"< {FAQ_TARGET_S:g} s",
            status(None if faq_median is None else faq_median < FAQ_TARGET_S),
        ),
        ("Latencia FAQ (p95)", fmt(value("faq_latency_p95_s"), "s", 2), "informativo", "—"),
        (
            "Cumplimiento comercial <180 s",
            fmt(compliance_pct, "%"),
            f"≥ {COMPLIANCE_TARGET_PCT:g} %",
            status(None if compliance_pct is None else compliance_pct >= COMPLIANCE_TARGET_PCT),
        ),
        (
            "Captura nocturna",
            fmt(value("night_capture_rate_pct"), "%"),
            f"{metrics.get('counts', {}).get('night_capture', 0)} solicitudes",
            "—",
        ),
        ("Conversión directa", fmt(value("direct_conversion_pct"), "%"), "informativo", "—"),
        ("Costo por consulta", fmt(value("cost_per_query_clp"), "CLP", 0), "informativo", "—"),
        ("Respuestas de IA", str(value("ai_replies")), "informativo", "—"),
        ("Reservas hechas por la IA", str(value("ai_bookings")), "informativo", "—"),
        ("Guardrails activados", str(value("ai_guardrail_hits")), "0 esperado", "—"),
    ]
    if shift:
        rows.append(("Sin respuesta ahora", str(shift.get("pending_human")), "0 esperado", "—"))

    width = max(len(row[0]) for row in rows)
    print(f"\nPiloto · últimos {args.days} días · {base}\n")
    for label, measured, target, state in rows:
        print(f"  {label:<{width}}  {measured:>12}   meta: {target:<14} {state}")

    blocking = [row[0] for row in rows if row[3] == "no cumple"]
    print()
    if blocking:
        print(f"Metas incumplidas: {', '.join(blocking)}")
    else:
        print("Todas las metas con objetivo se cumplen en esta ventana.")

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["indicador", "valor", "meta", "estado"])
            writer.writerows(rows)
        print(f"Exportado a {args.csv}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

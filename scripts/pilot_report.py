#!/usr/bin/env python3
"""Informe del piloto: lee las métricas del copiloto y las compara con las metas acordadas.

Uso:
    python scripts/pilot_report.py --days 14
    python scripts/pilot_report.py --days 14 --csv piloto.csv
    COPILOTO_URL=http://localhost:8100 PANEL_TOKEN=... python scripts/pilot_report.py

Las metas salen de la Unidad 2: FAQ bajo 10 s, primera respuesta comercial humana bajo 180 s en
al menos 90 % de las consultas del turno, y captura nocturna informada aparte.
"""

import argparse
import csv
import json
import os
import urllib.error
import urllib.request

FAQ_TARGET_S = 10.0
COMPLIANCE_TARGET_PCT = 90.0


def fetch(path: str, token: str | None = None) -> dict:
    request = urllib.request.Request(path, headers={"X-Panel-Token": token} if token else {})
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


def panel_token() -> str:
    """Toma la variable de entorno y, si no está, la lee del .env local (sin imprimirla)."""
    token = os.environ.get("PANEL_TOKEN", "")
    if token:
        return token
    try:
        with open(".env", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("PANEL_TOKEN="):
                    return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return ""


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

    try:
        metrics = fetch(f"{base}/metricas/data.json?days={args.days}")
    except (urllib.error.URLError, ValueError) as error:
        print(f"No pude leer las métricas en {base}: {error}", flush=True)
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

    rows = [
        ("Latencia FAQ (mediana)", fmt(value("faq_latency_median_s"), "s", 2), f"< {FAQ_TARGET_S:g} s",
         status(None if value("faq_latency_median_s") is None else value("faq_latency_median_s") < FAQ_TARGET_S)),
        ("Latencia FAQ (p95)", fmt(value("faq_latency_p95_s"), "s", 2), "informativo", "—"),
        ("Cumplimiento comercial <180 s", fmt(value("commercial_response_compliance_pct"), "%"),
         f"≥ {COMPLIANCE_TARGET_PCT:g} %",
         status(None if value("commercial_response_compliance_pct") is None
                else value("commercial_response_compliance_pct") >= COMPLIANCE_TARGET_PCT)),
        ("Captura nocturna", fmt(value("night_capture_rate_pct"), "%"),
         f"{metrics.get('counts', {}).get('night_capture', 0)} solicitudes", "—"),
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

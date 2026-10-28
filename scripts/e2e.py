"""Pruebas integrales locales; toda salida se limita a la tabla final sin secretos."""

import os
import subprocess
import sys
import time
import unicodedata
from contextlib import closing
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

ROOT = Path(__file__).resolve().parents[1]
CHATWOOT = "http://localhost:3000"
COPILOTO = "http://localhost:8100"
PMS = "http://localhost:8200"
POLL_SECONDS = 0.5
WAIT_SECONDS = 20.0
# Fechas relativas a hoy: una fecha fija vence y vuelve frágil la prueba
CHECKIN = date.today() + timedelta(days=150)
CHECKOUT = CHECKIN + timedelta(days=3)


def read_runtime():
    values = {}
    for raw in (ROOT / ".env.runtime").read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, value = line.partition("=")
        if not separator:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        else:
            value = value.split(" #", 1)[0].rstrip()
        values[key.strip()] = value
    for key in ("CHATWOOT_ACCOUNT_ID", "CHATWOOT_ADMIN_TOKEN", "CHATWOOT_WEBSITE_TOKEN"):
        if not values.get(key):
            raise ValueError("Missing runtime configuration")
    if not values["CHATWOOT_ACCOUNT_ID"].isdigit():
        raise ValueError("Invalid account configuration")
    return values


def safe_error(error):
    # No incluir str(error): las excepciones HTTP pueden contener URLs con credenciales.
    if isinstance(error, httpx.HTTPStatusError):
        return f"HTTP {error.response.status_code}"
    if isinstance(error, subprocess.TimeoutExpired):
        return "Docker compose exceeded its time limit"
    return type(error).__name__


def normalized(text):
    return "".join(character for character in unicodedata.normalize("NFD", text.casefold())
                   if not unicodedata.combining(character))


class Results:
    def __init__(self):
        self.rows = []

    def check(self, case, check, passed, detail):
        self.rows.append((case, check, "PASS" if passed else "FAIL", detail))
        return passed

    def show(self):
        rows = [("case", "check", "result", "detail"), *self.rows]
        widths = [max(len(str(row[index])) for row in rows) for index in range(4)]
        for row in rows:
            print(" | ".join(str(value).ljust(widths[index]) for index, value in enumerate(row)))
        return int(any(row[2] == "FAIL" for row in self.rows))


class Runner:
    def __init__(self, runtime, results):
        self.runtime = runtime
        self.results = results
        self.http = httpx.Client(timeout=5.0, trust_env=False)

    def close(self):
        self.http.close()

    def recreate(self, service, overrides):
        environment = os.environ.copy()
        environment.update(self.runtime)
        # Restaurar significa quitar las variables de turno, no fijarlas al valor de prueba.
        environment.pop("SHIFT_START", None)
        environment.pop("SHIFT_END", None)
        environment.update(overrides)
        environment["COMPOSE_PROJECT_NAME"] = "copiloto"
        command = ["docker", "compose", "-f", "infra/docker-compose.yml", "--project-directory", ".",
                   "up", "-d", "--force-recreate", service]
        process = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, timeout=180)
        if process.returncode:
            raise RuntimeError("Service recreation failed")
        self.wait_health(COPILOTO if service == "copiloto" else PMS)

    def wait_health(self, base_url):
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            try:
                if self.http.get(base_url + "/health", timeout=2).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(POLL_SECONDS)
        raise TimeoutError("Service health deadline exceeded")

    def staff_snapshot(self, conversation_id):
        base = f"{CHATWOOT}/api/v1/accounts/{self.runtime['CHATWOOT_ACCOUNT_ID']}"
        headers = {"api_access_token": self.runtime["CHATWOOT_ADMIN_TOKEN"]}
        response = self.http.get(f"{base}/conversations/{conversation_id}", headers=headers)
        response.raise_for_status()
        conversation = response.json()
        response = self.http.get(f"{base}/conversations/{conversation_id}/messages", headers=headers)
        response.raise_for_status()
        return conversation, response.json()["payload"]

    def verify_staff(self, case, guest, night=False, expected_status="open"):
        deadline = time.monotonic() + WAIT_SECONDS
        conversation, messages = {}, []
        while time.monotonic() < deadline:
            conversation, messages = self.staff_snapshot(guest.conversation_id)
            labels = conversation.get("labels", [])
            team = ((conversation.get("meta") or {}).get("team") or {}).get("name", "")
            note = any(message.get("private") is True
                       and (message.get("content") or "").startswith("Pre-información del copiloto")
                       and CHECKIN.isoformat() in (message.get("content") or "") for message in messages)
            ready = conversation.get("status") == expected_status
            if expected_status == "open":
                ready = ready and "comercial" in labels and normalized(team) == "recepcion" and note
                if night:
                    ready = ready and "nocturna" in labels
            if ready:
                break
            time.sleep(POLL_SECONDS)
        self.results.check(case, "conversation status", conversation.get("status") == expected_status,
                           f"Expected {expected_status}")
        if expected_status == "pending":
            return
        self.results.check(case, "commercial label", "comercial" in labels, "Expected comercial")
        self.results.check(case, "reception team", normalized(team) == "recepcion", "Expected recepción")
        self.results.check(case, "private dated note", note, f"Private pre-information includes {CHECKIN.isoformat()}")
        if night:
            self.results.check(case, "night label", "nocturna" in labels, "Expected nocturna")

    def faq(self):
        with closing(Guest(self.runtime)) as guest:
            elapsed, _ = guest.send_and_wait("¿tienen piscina?", "piscina temperada", timeout=10)
            self.results.check("FAQ", "answer latency", elapsed <= 10, f"{elapsed:.2f} s; limit 10 s")
            self.verify_staff("FAQ", guest, expected_status="pending")

    def availability(self, case, night=False, opening=None, down=False):
        with closing(Guest(self.runtime)) as guest:
            for content, expected in (("quiero reservar", "necesito tus fechas"),
                                      (f"{CHECKIN:%d/%m/%Y} al {CHECKOUT:%d/%m/%Y}", "¿Cuántos adultos"),
                                      ("2", "¿Y niños")):
                elapsed, _ = guest.send_and_wait(content, expected)
                self.results.check(case, f"reply to {content}", True, f"Expected response visible in {elapsed:.2f} s")
            if down:
                elapsed, _ = guest.send_and_wait("0", "Recepción verificará cupos")
                self.results.check(case, "PMS fallback", True, f"Fallback visible in {elapsed:.2f} s")
                # El PMS caído deriva inmediatamente: no enviar una selección después del traspaso.
                guest.wait_for("Ya pasé tu consulta a recepción", set(), time.monotonic() + WAIT_SECONDS)
            else:
                elapsed, availability = guest.send_and_wait("0", "Disponible según lectura del PMS")
                pending = "Pendiente de confirmación por recepción" in (availability.get("content") or "")
                self.results.check(case, "pending confirmation", pending,
                                   f"Availability visible in {elapsed:.2f} s; human confirmation required")
                guest.wait_for("¿Cuál te interesa?", set(), time.monotonic() + WAIT_SECONDS,
                               content_type="input_select")
                closing_text = "fuera del horario de recepción" if night else "Ya pasé tu consulta a recepción"
                elapsed, closing_message = guest.send_and_wait("1", closing_text)
                self.results.check(case, "handoff closing", True, f"Closing visible in {elapsed:.2f} s")
                if night:
                    self.results.check(case, "opening hour", opening in (closing_message.get("content") or ""),
                                       f"Expected opening hour {opening}")
            outgoing = [message for message in guest.messages() if message.get("message_type") == 1]
            location = next((index for index, message in enumerate(outgoing)
                             if (message.get("content") or "").startswith("Ubicación:")), None)
            dates = next((index for index, message in enumerate(outgoing)
                          if "necesito tus fechas" in (message.get("content") or "")), None)
            ordered = location is not None and dates is not None and location < dates
            self.results.check(case, "location before dates", ordered, "Guest-visible outgoing message order")
            self.verify_staff(case, guest, night=night)

    def metrics(self):
        response = self.http.get(COPILOTO + "/metricas/data.json", params={"days": 1})
        response.raise_for_status()
        data = response.json()
        for key, actual, minimum in (("faq_answered", data.get("counts", {}).get("faq_answered", 0), 1),
                                     ("handoff", data.get("counts", {}).get("handoff", 0), 3),
                                     ("queries", data.get("queries", 0), 1)):
            self.results.check("metrics", key, isinstance(actual, (int, float)) and actual >= minimum,
                               f"Expected cumulative count >= {minimum}")


class Guest:
    def __init__(self, runtime):
        self.http = httpx.Client(timeout=5.0, trust_env=False)
        self.params = {"website_token": runtime["CHATWOOT_WEBSITE_TOKEN"], "locale": "es"}
        self.conversation_id = None
        try:
            response = self.http.post(CHATWOOT + "/api/v1/widget/config", params=self.params, json={})
            response.raise_for_status()
            self.headers = {"X-Auth-Token": response.json()["website_channel_config"]["auth_token"]}
        except BaseException:
            self.http.close()
            raise

    def close(self):
        self.http.close()

    def messages(self, timeout=5.0):
        response = self.http.get(CHATWOOT + "/api/v1/widget/messages", params=self.params,
                                 headers=self.headers, timeout=timeout)
        response.raise_for_status()
        return sorted(response.json()["payload"], key=lambda message: message["id"])

    def wait_for(self, expected, previous_ids, deadline, content_type=None):
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            try:
                messages = self.messages(timeout=max(0.01, min(2, remaining)))
                for message in messages:
                    if message["id"] in previous_ids or message.get("message_type") != 1:
                        continue
                    if content_type is not None and message.get("content_type") != content_type:
                        continue
                    if expected in (message.get("content") or ""):
                        return message
            except httpx.TransportError:
                pass
            time.sleep(min(POLL_SECONDS, max(0, deadline - time.monotonic())))
        raise TimeoutError("Expected guest-visible bot response did not arrive")

    def send_and_wait(self, content, expected, timeout=WAIT_SECONDS):
        previous_ids = {message["id"] for message in self.messages()} if self.conversation_id else set()
        started = time.monotonic()
        response = self.http.post(CHATWOOT + "/api/v1/widget/messages", params=self.params,
                                  headers=self.headers, json={"message": {
                                      "content": content, "timestamp": "2026-10-27T12:00:00-03:00",
                                      "referer_url": "http://localhost:8080/"}})
        response.raise_for_status()
        conversation_id = response.json()["conversation_id"]
        if self.conversation_id is not None and conversation_id != self.conversation_id:
            raise ValueError("Widget conversation changed unexpectedly")
        self.conversation_id = conversation_id
        message = self.wait_for(expected, previous_ids, started + timeout)
        return time.monotonic() - started, message


def run_case(results, name, operation):
    try:
        operation()
    except Exception as error:
        results.check(name, "execution", False, safe_error(error))


def main():
    results = Results()
    runner = None
    try:
        runtime = read_runtime()
        runner = Runner(runtime, results)
        try:
            runner.recreate("pms-mock", {"SIMULATE_DOWN": "0"})
            runner.recreate("copiloto", {"SHIFT_START": "00:00", "SHIFT_END": "00:00", "SIMULATE_DOWN": "0"})
            results.check("setup", "services ready", True, "PMS available; reception forced in shift")
            run_case(results, "FAQ", runner.faq)
            run_case(results, "availability", lambda: runner.availability("availability"))

            def night_case():
                now = datetime.now(ZoneInfo("America/Santiago"))
                opening = (now + timedelta(hours=2)).strftime("%H:%M")
                ending = (now + timedelta(hours=3)).strftime("%H:%M")
                runner.recreate("copiloto", {"SHIFT_START": opening, "SHIFT_END": ending, "SIMULATE_DOWN": "0"})
                runner.availability("out of hours", night=True, opening=opening)

            run_case(results, "out of hours", night_case)

            def down_case():
                runner.recreate("copiloto", {
                    "SHIFT_START": "00:00", "SHIFT_END": "00:00", "SIMULATE_DOWN": "0"})
                runner.recreate("pms-mock", {"SIMULATE_DOWN": "1"})
                runner.availability("PMS down", down=True)

            run_case(results, "PMS down", down_case)
            run_case(results, "metrics", runner.metrics)
        finally:
            # Ambos intentos son independientes: un fallo no debe impedir la otra restauración.
            for service in ("copiloto", "pms-mock"):
                try:
                    runner.recreate(service, {"SIMULATE_DOWN": "0"})
                    results.check("restore", service, True, "Default shift / SIMULATE_DOWN=0 restored; health 200")
                except Exception as error:
                    results.check("restore", service, False, safe_error(error))
    except KeyboardInterrupt:
        results.check("run", "interrupted", False, "Interrupted; restoration attempted")
    except Exception as error:
        results.check("setup", "execution", False, safe_error(error))
    finally:
        if runner is not None:
            runner.close()
    return results.show()


if __name__ == "__main__":
    sys.exit(main())

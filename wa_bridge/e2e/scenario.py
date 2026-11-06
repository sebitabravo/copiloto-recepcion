"""Escenario E2E del canal de WhatsApp. Corre DENTRO del contenedor wa-bridge (scripts/wa-e2e.sh).

Usa el OpenWA simulado (http://openwa:2785) y el Chatwoot real del stack: valida lo que ve el huésped
(`/_sent`) contra lo que ve recepción (API de Chatwoot). Con `--sla` agrega la prueba de 195 s del cronómetro.
"""

import os
import random
import sqlite3
import sys
import time

import httpx

FAKE = os.environ["OPENWA_API_URL"]
CHATWOOT = f"{os.environ['CHATWOOT_URL']}/api/v1/accounts/{os.environ['CHATWOOT_ACCOUNT_ID']}"
ADMIN = {"api_access_token": os.environ["CHATWOOT_ADMIN_TOKEN"]}
DB = os.environ["WA_BRIDGE_DB_PATH"]
RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(ok), detail))
    print(("PASA   " if ok else "FALLA  ") + name + (f"  [{detail}]" if detail and not ok else ""), flush=True)


def new_chat() -> str:
    return f"56955{random.randint(1000000, 9999999)}@c.us"


def inject(chat: str, body: str = "", **extra) -> int:
    response = httpx.post(f"{FAKE}/_inject", json={"chatId": chat, "body": body, **extra}, timeout=15)
    return response.json()["bridge_status"]


def sent_to(chat: str) -> list[str]:
    return [m["text"] for m in httpx.get(f"{FAKE}/_sent", timeout=10).json() if m["chatId"] == chat]


def wait(condition, timeout: float = 25.0, step: float = 0.7):
    end = time.time() + timeout
    while time.time() < end:
        value = condition()
        if value:
            return value
        time.sleep(step)
    return None


def conversations(chat: str) -> list[int]:
    db = sqlite3.connect(DB)
    return [row[0] for row in db.execute(
        "SELECT conversation_id FROM conversations WHERE chat_id = ? ORDER BY created_at, rowid", (chat,))]


def conversation(conversation_id: int) -> dict:
    return httpx.get(f"{CHATWOOT}/conversations/{conversation_id}", headers=ADMIN, timeout=10).json()


def messages(conversation_id: int) -> list[dict]:
    return httpx.get(f"{CHATWOOT}/conversations/{conversation_id}/messages", headers=ADMIN,
                     timeout=10).json()["payload"]


def agent_post(conversation_id: int, content: str, private: bool) -> None:
    httpx.post(f"{CHATWOOT}/conversations/{conversation_id}/messages", headers=ADMIN, timeout=10,
               json={"content": content, "message_type": "outgoing", "private": private}).raise_for_status()


def has(chat: str, needle: str) -> bool:
    return any(needle in text for text in sent_to(chat))


def run() -> None:
    httpx.post(f"{FAKE}/_reset", timeout=10)

    # 1. Primer contacto: saludo + menú numerado, conversación pendiente en el canal API
    chat = new_chat()
    check("firma inválida rechazada (401)", httpx.post(
        "http://localhost:8400/webhooks/openwa", content=b"{}", headers={"x-openwa-signature": "sha256=00"}
    ).status_code == 401)
    check("webhook firmado aceptado", inject(chat, "Hola") == 200)
    check("saludo y menú numerado llegan al huésped",
          wait(lambda: has(chat, "Responde con el número de la opción")), str(sent_to(chat)))
    def in_order() -> bool:
        texts = sent_to(chat)
        marks = [next((i for i, t in enumerate(texts) if needle in t), None)
                 for needle in ("Soy el Copiloto", "Ubicación:", "Responde con el número")]
        return None not in marks and marks == sorted(marks)

    check("saludo, ubicación y menú llegan en ese orden", wait(in_order), str(sent_to(chat)))
    conv = wait(lambda: conversations(chat))
    check("se creó una conversación mapeada", bool(conv))
    first = conv[0]
    info = conversation(first)
    check("canal Channel::Api y estado pending", info["meta"]["channel"] == "Channel::Api"
          and info["status"] == "pending", f"{info['meta']['channel']} {info['status']}")
    check("el mensaje del huésped llegó como incoming con su texto",
          any(m["message_type"] == 0 and m["content"] == "Hola" for m in messages(first)))

    # 2. Opción del menú
    before = len(sent_to(chat))
    inject(chat, "1")
    check("la opción 1 (Ubicación) recibe respuesta", wait(lambda: len(sent_to(chat)) > before),
          str(sent_to(chat)[-1:]))

    # 3. Eco y duplicados
    before = len(sent_to(chat))
    count = len(messages(first))
    inject(chat, "eco del bot", fromMe=True)
    inject(chat, "grupo", isGroup=True)
    inject(chat, "otra cuenta", sessionId="otra-cuenta")
    time.sleep(4)
    check("fromMe, grupos y otras sesiones se ignoran", len(sent_to(chat)) == before
          and len(messages(first)) == count)
    dup = f"dup-{random.randint(1, 10**9)}"
    inject(chat, "mensaje repetido", id=dup)
    inject(chat, "mensaje repetido", id=dup)
    time.sleep(5)
    check("un webhook duplicado se procesa una sola vez",
          sum(1 for m in messages(first) if m["content"] == "mensaje repetido") == 1)

    # 4. Nota de voz
    inject(chat, "", type="voice")
    check("nota de voz: aviso de solo texto", wait(lambda: has(chat, "solo puedo leer mensajes de texto")))

    # 5. Ráfaga concurrente: misma conversación, ningún mensaje perdido
    burst = new_chat()
    inject(burst, "Hola")
    wait(lambda: conversations(burst))
    for number in range(3):
        inject(burst, f"ráfaga {number}")
    check("ráfaga de 3 mensajes sin perder ninguno ni duplicar conversación", wait(
        lambda: sum(1 for m in messages(conversations(burst)[0]) if (m["content"] or "").startswith("ráfaga")) == 3
        and len(conversations(burst)) == 1), str(conversations(burst)))

    # 6. Derivación a recepción, nota privada, respuesta humana
    hand = new_chat()
    inject(hand, "Hola")
    wait(lambda: conversations(hand))
    handoff_conv = conversations(hand)[0]
    inject(hand, "quiero hablar con una persona")
    check("la derivación abre la conversación para recepción",
          wait(lambda: conversation(handoff_conv)["status"] == "open"), conversation(handoff_conv)["status"])
    note = "NOTA-INTERNA-SLA-vencido-no-debe-llegar"
    agent_post(handoff_conv, note, private=True)
    time.sleep(6)
    check("la nota privada NO llega al huésped", not has(hand, note) and not has(hand, "NOTA-INTERNA"))
    reply = "Hola, soy de recepción, ¿en qué te ayudo?"
    agent_post(handoff_conv, reply, private=False)
    check("la respuesta pública de recepción llega a WhatsApp", wait(lambda: has(hand, reply), 20))

    # 7. Conversación resuelta: el siguiente mensaje abre una nueva
    httpx.post(f"{CHATWOOT}/conversations/{handoff_conv}/toggle_status", headers=ADMIN, json={"status": "resolved"})
    inject(hand, "Hola otra vez")
    check("tras resolver, un nuevo mensaje abre otra conversación",
          wait(lambda: len(conversations(hand)) == 2), str(conversations(hand)))

    # 8. Cronómetro de 180 s (opcional por duración)
    if "--sla" in sys.argv:
        sla = new_chat()
        inject(sla, "Hola")
        wait(lambda: conversations(sla))
        sla_conv = conversations(sla)[0]
        inject(sla, "hablar con recepción")
        wait(lambda: conversation(sla_conv)["status"] == "open")
        started = time.time()
        check("a los ~130 s aparece la etiqueta sla-ambar", wait(
            lambda: "sla-ambar" in conversation(sla_conv).get("labels", []), 140, 5),
              str(conversation(sla_conv).get("labels")))
        check("a los ~195 s aparece sla-vencido", wait(
            lambda: "sla-vencido" in conversation(sla_conv).get("labels", []), 195 - (time.time() - started), 5),
              str(conversation(sla_conv).get("labels")))
        check("la nota 'SLA vencido' no se entregó al huésped", not has(sla, "SLA vencido"))
        agent_post(sla_conv, "Disculpa la demora, ya te atiendo.", private=False)
        check("una respuesta tardía de recepción igual llega al huésped",
              wait(lambda: has(sla, "Disculpa la demora"), 20))


if __name__ == "__main__":
    run()
    failed = [name for name, ok, _ in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} verificaciones pasan")
    sys.exit(1 if failed else 0)

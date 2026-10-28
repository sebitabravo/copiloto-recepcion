"""Límite de ventana deslizante por IP para los endpoints de lectura (no aplica a los webhooks firmados)."""

import time
from collections import defaultdict, deque
from collections.abc import Callable

from fastapi import HTTPException, Request


class SlidingWindowLimiter:
    def __init__(self, max_requests: int, window_s: float = 60.0, clock: Callable[[], float] = time.time):
        self.max_requests = max_requests
        self.window_s = window_s
        self.clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> float | None:
        """None si la solicitud pasa; si no, los segundos hasta que se libere un cupo."""
        now = self.clock()
        hits = self._hits[key]
        while hits and now - hits[0] >= self.window_s:
            hits.popleft()
        if len(hits) >= self.max_requests:
            return self.window_s - (now - hits[0])
        hits.append(now)
        if len(self._hits) > 10_000:
            self._hits = defaultdict(deque, {k: v for k, v in self._hits.items() if v})
        return None

    def dependency(self):
        """Dependencia de FastAPI. Usa la IP directa: no confía en X-Forwarded-For sin un proxy declarado."""
        async def enforce(request: Request) -> None:
            key = request.client.host if request.client else "desconocido"
            wait = self.check(key)
            if wait is not None:
                raise HTTPException(status_code=429, detail="Demasiadas solicitudes",
                                    headers={"Retry-After": str(int(wait) + 1)})
        return enforce

"""Configuración de pruebas: las funciones async corren con el plugin anyio que trae starlette."""

import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"


def pytest_collection_modifyitems(items):
    for item in items:
        if item.get_closest_marker("anyio") is None and getattr(item.function, "__code__", None) \
                and item.function.__code__.co_flags & 0x80:
            item.add_marker(pytest.mark.anyio)

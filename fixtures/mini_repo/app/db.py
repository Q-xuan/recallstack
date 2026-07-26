"""Persistence helpers."""

_STORE: list[dict] = []


def save(data: dict) -> dict:
    _STORE.append(data)
    return data

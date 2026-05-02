import json
import os
from threading import Lock

_LOCK = Lock()
_DATA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "context_data.json",
)


def _empty() -> dict:
    return {"context": ""}


def _ensure_file() -> None:
    if not os.path.exists(_DATA_PATH):
        with open(_DATA_PATH, "w", encoding="utf-8") as f:
            json.dump(_empty(), f, indent=2)


def _migrate(data: dict) -> dict:
    """Accept old multi-category shape and fold it into a single string."""
    if "context" in data and isinstance(data["context"], str):
        return {"context": data["context"]}
    parts = []
    for k, v in data.items():
        if isinstance(v, str) and v.strip():
            parts.append(f"{k.replace('_', ' ').title()}: {v.strip()}")
    return {"context": "\n\n".join(parts)}


def load_context() -> dict:
    with _LOCK:
        _ensure_file()
        with open(_DATA_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return _migrate(data)


def save_context(text: str) -> dict:
    with _LOCK:
        _ensure_file()
        data = {"context": text or ""}
        with open(_DATA_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return data

import json
from pathlib import Path
from typing import Any


DATA_DIR = Path(__file__).resolve().parents[2] / "data"
HISTORY_FILE = DATA_DIR / "quiz_history.json"
MAX_HISTORY_ITEMS = 500

def load_history() -> list[dict[str, Any]]:
    if not HISTORY_FILE.exists():
        return []
    
    try:
        with open(HISTORY_FILE, "r", encoding = "utf-8") as file:
            data = json.load(file)

    except (json.JSONDecodeError, OSError):
        return []
    
    return data if isinstance(data, list) else []

def append_attempt(attempt: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    history = load_history()
    history.insert(0, attempt)
    history = history[:MAX_HISTORY_ITEMS]

    with HISTORY_FILE.open("w", encoding="utf-8") as file:
        json.dump(history, file, ensure_ascii=False, indent=2)
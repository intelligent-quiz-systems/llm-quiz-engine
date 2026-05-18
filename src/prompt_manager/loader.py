# src/prompt_manager/loader.py
from pathlib import Path
import json
from typing import Dict, Any


def load_prompts_from_directory(directory: Path) -> Dict[str, Dict[str, Any]]:
    """
    Wczytuje wszystkie pliki .json z katalogu i zwraca słownik {nazwa_szablonu: zawartość}
    Obsługuje zarówno stare jak i nowe formaty z wersjonowaniem.
    """
    prompts = {}

    for file_path in directory.glob("*.json"):
        try:
            with file_path.open("r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                print(f"[ERR] File {file_path.name}: content is not a dict")
                continue

            name = file_path.stem
            prompts[name] = data
            print(f"[OK] Wczytano szablon: {name}")

        except json.JSONDecodeError as e:
            print(f"[ERR] JSON syntax error in {file_path.name}: {e}")
        except Exception as e:
            print(f"[ERR] Unknown error loading {file_path.name}: {e}")

    return prompts
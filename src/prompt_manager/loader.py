# src/prompt_manager/loader.py
from pathlib import Path
import json
from typing import Dict, Any


def load_prompts_from_directory(directory: Path) -> Dict[str, Dict[str, Any]]:
    """
    Wczytuje wszystkie pliki .json z katalogu i zwraca słownik {nazwa_pliku: zawartość}
    """
    prompts = {}

    for file_path in directory.glob("*.json"):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                # nazwa bez rozszerzenia
                name = file_path.stem
                prompts[name] = data
        except Exception as e:
            print(f"Błąd podczas wczytywania {file_path}: {e}")

    return prompts
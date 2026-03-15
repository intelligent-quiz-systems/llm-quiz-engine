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
            with file_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Walidacja – sprawdzamy, czy plik ma wymaganą strukturę
            if not isinstance(data, dict):
                print(f"✗ Błąd w pliku {file_path.name}: zawartość nie jest słownikiem (dict)")
                continue
            
            if "system" not in data or "user" not in data:
                print(f"✗ Błąd w pliku {file_path.name}: brakuje wymaganego klucza 'system' lub 'user'")
                continue
            
            if not isinstance(data["system"], str) or not isinstance(data["user"], str):
                print(f"✗ Błąd w pliku {file_path.name}: klucze 'system' i 'user' muszą być tekstem (string)")
                continue
            
            # Jeśli wszystko OK – dodajemy
            name = file_path.stem
            prompts[name] = data
            print(f"✓ Wczytano szablon: {name}")

        except json.JSONDecodeError as e:
            print(f"✗ Błąd składni JSON w pliku {file_path.name}: {e}")
        except Exception as e:
            print(f"✗ Nieznany błąd podczas wczytywania {file_path.name}: {e}")

    return prompts
# src/prompt_manager/manager.py
from pathlib import Path
from typing import Dict, Any, Optional

from .loader import load_prompts_from_directory


class PromptManager:
    """
    Główna klasa zarządzająca promptami.
    Ładuje prompty z katalogu JSON, pozwala budować je z parametrami.
    """

    def __init__(self, prompts_dir: str | Path = "data/prompts"):
        self.prompts_dir = Path(prompts_dir)
        self.prompts: Dict[str, Dict[str, Any]] = {}
        self.load_prompts()

    def load_prompts(self) -> None:
        """Wczytuje wszystkie prompty z katalogu data/prompts"""
        self.prompts = load_prompts_from_directory(self.prompts_dir)

    def get_prompt(self, template_name: str) -> Optional[Dict[str, Any]]:
        """Zwraca szablon promptu po nazwie"""
        return self.prompts.get(template_name)

    def build_prompt(self, template_name: str, **kwargs) -> Optional[str]:
        """
        Buduje gotowy prompt z szablonu i parametrów.
        Przykład: build_prompt("multiple_choice", topic="Groq", difficulty="łatwe")
        """
        template = self.get_prompt(template_name)
        if not template:
            return None

        system = template.get("system", "")
        user_template = template.get("user", "")

        # Podstawianie parametrów w user
        try:
            user = user_template.format(**kwargs)
        except KeyError as e:
            raise ValueError(f"Brak parametru {e} w szablonie {template_name}")

        return f"{system}\n\n{user}"
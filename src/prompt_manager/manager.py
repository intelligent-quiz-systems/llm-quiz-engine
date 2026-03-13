# src/prompt_manager/manager.py
from pathlib import Path
from typing import Dict, Any, Optional

from .loader import load_prompts_from_directory
from .exceptions import PromptNotFoundError
from .groq_client import GroqClient  # ← ważny import!


class PromptManager:
    """
    Główna klasa zarządzająca promptami.
    Ładuje prompty z katalogu JSON, pozwala budować je z parametrami.
    """

    def __init__(self, prompts_dir: str | Path = "data/prompts", api_key: Optional[str] = None):
        self.prompts_dir = Path(prompts_dir)
        self.prompts: Dict[str, Dict[str, Any]] = {}
        self.groq = GroqClient(api_key=api_key)  # ← tutaj inicjujemy Groq!
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

    def generate(self, template_name: str, **kwargs) -> Optional[str]:
        """
        Generuje pełny prompt i wysyła go do Groq.
        Zwraca wygenerowaną odpowiedź lub None w razie błędu.
        """
        prompt = self.build_prompt(template_name, **kwargs)
        if not prompt:
            return None

        return self.groq.generate_response(prompt)

    def generate_from_image_description(
        self,
        opis_obrazu: str,
        template_name: str = "image_based",
        **kwargs
    ) -> Optional[str]:
        """
        Generuje pytanie quizowe na podstawie tekstowego opisu obrazu.
        Używa szablonu image_based.json.
        """
        template = self.get_prompt(template_name)
        if not template:
            raise PromptNotFoundError(template_name)

        # Podstawiamy opis obrazu + pozostałe parametry
        prompt = self.build_prompt(template_name, opis_obrazu=opis_obrazu, **kwargs)
        if not prompt:
            return None

        return self.groq.generate_response(prompt)
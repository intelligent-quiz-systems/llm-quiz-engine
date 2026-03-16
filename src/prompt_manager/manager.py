# Obsługa wizji (end-to-end z obrazów) – wyłączona na razie (brak dostępu do modelu)
# Można włączyć po zmianie modelu / klucza API

# src/prompt_manager/manager.py
from pathlib import Path
from typing import Dict, Any, Optional

from .loader import load_prompts_from_directory
from .exceptions import PromptNotFoundError
from .groq_client import GroqClient
from .vision import VisionClient  # ← dodany import!


class PromptManager:
    """
    Główna klasa zarządzająca promptami.
    Ładuje prompty z katalogu JSON, pozwala budować je z parametrami.
    """

    def __init__(self, prompts_dir: str | Path = "data/prompts", api_key: Optional[str] = None):
        self.prompts_dir = Path(prompts_dir)
        self.prompts: Dict[str, Dict[str, Any]] = {}
        self.groq = GroqClient(api_key=api_key)
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

        prompt = self.build_prompt(template_name, opis_obrazu=opis_obrazu, **kwargs)
        if not prompt:
            return None

        return self.groq.generate_response(prompt)

    def list_templates(self, sort: bool = True) -> list[str]:
        """
        Zwraca listę nazw wszystkich dostępnych szablonów promptów.
        """
        templates = list(self.prompts.keys())
        if sort:
            templates.sort()
        return templates

    def generate_from_image(
        self,
        image_path: str | Path,
        model: str = "llama-4-scout-17b-16e-instruct",
        temat: str = "ogólny",
        poziom: str = "średni"
    ) -> Optional[str]:
        """
        Generuje pytanie quizowe bezpośrednio z obrazu (end-to-end vision na Groq).
        """
        try:
            vision = VisionClient()
            return vision.generate_question_from_image(
                image_path=image_path,
                model=model,
                temat=temat,
                poziom=poziom
            )
        except FileNotFoundError as e:
            print(f"Błąd: nie znaleziono obrazu {image_path}")
            return None
        except Exception as e:
            print(f"Błąd podczas generowania z obrazu: {e}")
            return None
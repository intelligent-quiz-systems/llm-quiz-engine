# src/prompt_manager/manager.py
from pathlib import Path
from typing import Dict, Any, Optional

from .loader import load_prompts_from_directory


class PromptManager:
    """
    Czysty Prompt Manager – tylko ładuje i udostępnia szablony promptów.
    Wspiera wersjonowanie promptów.
    Komunikacja z LLM jest w module src/llm.
    """

    def __init__(self, prompts_dir: str | Path = "data/prompts"):
        self.prompts_dir = Path(prompts_dir)
        self.prompts: Dict[str, Dict[str, Any]] = {}
        self.load_prompts()

    def load_prompts(self) -> None:
        """Wczytuje wszystkie prompty z katalogu data/prompts"""
        self.prompts = load_prompts_from_directory(self.prompts_dir)

    def list_templates(self) -> list[str]:
        """Zwraca listę wszystkich dostępnych szablonów"""
        return sorted(self.prompts.keys())

    def get_prompt(self, template_name: str, version: str = "v1") -> Optional[Dict[str, Any]]:
        """
        Zwraca szablon promptu po nazwie i wersji.
        Jeśli wersja nie istnieje, zwraca None.
        """
        template = self.prompts.get(template_name)
        if not template:
            return None

        # Nowa struktura z wersjami
        if "versions" in template and isinstance(template["versions"], dict):
            return template["versions"].get(version)

        # Stara struktura (bez wersjonowania) – zwracamy cały szablon
        return template

    def get_default_version(self, template_name: str) -> str:
        """Zwraca domyślną wersję szablonu (jeśli jest zdefiniowana)"""
        template = self.prompts.get(template_name)
        if template and "default_version" in template:
            return template["default_version"]
        return "v1"  # domyślna wersja jeśli nie podano
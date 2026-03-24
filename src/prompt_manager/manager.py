# src/prompt_manager/manager.py
from pathlib import Path
from typing import Dict, Any, Optional

from .loader import load_prompts_from_directory


class PromptManager:
    """
    Czysty Prompt Manager – odpowiedzialny tylko za ładowanie i udostępnianie promptów.
    Wspiera wersjonowanie promptów (v1, v2, ...).
    Komunikacja z LLM odbywa się w module src/llm.
    """

    def __init__(self, prompts_dir: str | Path = "data/prompts"):
        self.prompts_dir = Path(prompts_dir)
        self.prompts: Dict[str, Dict[str, Any]] = {}
        self.load_prompts()

    def load_prompts(self) -> None:
        """Wczytuje wszystkie prompty z katalogu data/prompts"""
        self.prompts = load_prompts_from_directory(self.prompts_dir)

    def list_templates(self) -> list[str]:
        """Zwraca posortowaną listę wszystkich dostępnych szablonów"""
        return sorted(self.prompts.keys())

    def get_prompt(self, template_name: str, version: str = None) -> Optional[Dict[str, Any]]:
        """
        Zwraca szablon promptu.
        
        Args:
            template_name: nazwa szablonu (np. "multiple_choice")
            version: wersja promptu (np. "v1", "v2"). Jeśli None - zwraca domyślną wersję.
        """
        template = self.prompts.get(template_name)
        if not template:
            return None

        # Jeśli szablon ma strukturę z wersjami
        if "versions" in template and isinstance(template["versions"], dict):
            if version is None:
                version = template.get("default_version", "v1")
            return template["versions"].get(version)

        # Stara struktura (bez wersjonowania) - zwracamy cały szablon
        return template

    def get_system_prompt(self, template_name: str, version: str = None) -> Optional[str]:
        """Zwraca tylko część 'system' wybranego promptu"""
        prompt = self.get_prompt(template_name, version)
        return prompt.get("system") if prompt else None

    def get_user_prompt(self, template_name: str, version: str = None) -> Optional[str]:
        """Zwraca tylko część 'user' wybranego promptu"""
        prompt = self.get_prompt(template_name, version)
        return prompt.get("user") if prompt else None

    def get_default_version(self, template_name: str) -> str:
        """Zwraca domyślną wersję szablonu"""
        template = self.prompts.get(template_name)
        if template and "default_version" in template:
            return template["default_version"]
        return "v1"  # fallback
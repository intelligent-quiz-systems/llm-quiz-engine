# src/prompt_manager/manager.py
from pathlib import Path
from typing import Dict, Any, Optional, List

from .loader import load_prompts_from_directory


class PromptManager:
    """
    Prompt Manager – odpowiedzialny tylko za zarządzanie promptami.
    Wspiera wersjonowanie: v1, v2, v3... 
    Umożliwia dodawanie nowych wersji promptów oraz powrót do poprzednich.
    """

    def __init__(self, prompts_dir: str | Path = "data/prompts"):
        self.prompts_dir = Path(prompts_dir)
        self.prompts: Dict[str, Dict[str, Any]] = {}
        self.load_prompts()

    def load_prompts(self) -> None:
        """Wczytuje wszystkie prompty z katalogu data/prompts"""
        self.prompts = load_prompts_from_directory(self.prompts_dir)

    def list_templates(self) -> List[str]:
        """Zwraca posortowaną listę wszystkich szablonów"""
        return sorted(self.prompts.keys())

    def list_versions(self, template_name: str) -> List[str]:
        """Zwraca listę wszystkich wersji danego szablonu"""
        template = self.prompts.get(template_name)
        if not template or "versions" not in template:
            return ["v1"] if template else []
        return sorted(template["versions"].keys())

    def get_default_version(self, template_name: str) -> str:
        """Zwraca domyślną wersję szablonu"""
        template = self.prompts.get(template_name)
        if template and "default_version" in template:
            return template["default_version"]
        return "v1"

    def get_prompt(self, template_name: str, version: str = None) -> Optional[Dict[str, Any]]:
        """
        Zwraca szablon promptu w podanej wersji.
        Jeśli wersja nie jest podana - zwraca domyślną wersję.
        """
        template = self.prompts.get(template_name)
        if not template:
            return None

        # Nowa struktura z wersjonowaniem
        if "versions" in template and isinstance(template["versions"], dict):
            if version is None:
                version = self.get_default_version(template_name)
            return template["versions"].get(version)

        # Stara struktura (bez wersjonowania)
        return template

    def get_system_prompt(self, template_name: str, version: str = None) -> Optional[str]:
        """Zwraca tylko część 'system' wybranego promptu"""
        prompt = self.get_prompt(template_name, version)
        return prompt.get("system") if prompt else None

    def get_user_prompt(self, template_name: str, version: str = None) -> Optional[str]:
        """Zwraca tylko część 'user' wybranego promptu"""
        prompt = self.get_prompt(template_name, version)
        return prompt.get("user") if prompt else None
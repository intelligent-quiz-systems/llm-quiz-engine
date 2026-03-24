# src/prompt_manager/manager.py
from pathlib import Path
from typing import Dict, Any, Optional

from .loader import load_prompts_from_directory


class PromptManager:
    """
    Czysty Prompt Manager – tylko ładuje i udostępnia szablony promptów.
    Nie komunikuje się z LLM (to jest w module src/llm).
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

    def get_prompt(self, template_name: str) -> Optional[Dict[str, Any]]:
        """Zwraca szablon promptu po nazwie"""
        return self.prompts.get(template_name)

    def get_prompt_version(self, template_name: str, version: str = "v1") -> Optional[Dict[str, Any]]:
        """
        Zwraca konkretną wersję promptu.
        Przykład: get_prompt_version("multiple_choice", "v2")
        """
        template = self.get_prompt(template_name)
        if not template:
            return None
        
        # Jeśli szablon ma już wersje (słownik wersji)
        if "versions" in template and version in template["versions"]:
            return template["versions"][version]
        
        # Jeśli szablon jest stary (bez wersjonowania) – zwracamy cały szablon
        return template
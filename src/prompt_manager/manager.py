# src/prompt_manager/manager.py
from pathlib import Path
from typing import Dict, Any, Optional

from .loader import load_prompts_from_directory


class PromptManager:
    """
    Prompt Manager – tylko ładuje i udostępnia szablony promptów.
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
        return list(self.prompts.keys())

    def get_prompt(self, template_name: str) -> Optional[Dict[str, Any]]:
        """Zwraca szablon promptu po nazwie"""
        return self.prompts.get(template_name)
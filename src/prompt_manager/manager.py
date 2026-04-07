# src/prompt_manager/manager.py
from pathlib import Path
from typing import Dict, Any, Optional, List
import json

from .loader import load_prompts_from_directory


class PromptManager:
    """
    Prompt Manager – odpowiedzialny tylko za zarządzanie promptami.
    Wspiera wersjonowanie (v1, v2, ...).
    Umożliwia programistyczne dodawanie nowych promptów i wersji.
    Komunikacja z LLM odbywa się w module src/llm.
    """

    def __init__(self, prompts_dir: str | Path = "data/prompts"):
        self.prompts_dir = Path(prompts_dir)
        self.prompts: Dict[str, Dict[str, Any]] = {}
        self.load_prompts()

    def load_prompts(self) -> None:
        """Wczytuje wszystkie prompty z katalogu data/prompts"""
        self.prompts = load_prompts_from_directory(self.prompts_dir)

    def list_templates(self) -> List[str]:
        """Zwraca posortowaną listę wszystkich dostępnych szablonów"""
        return sorted(self.prompts.keys())

    def list_versions(self, template_name: str) -> List[str]:
        """Zwraca listę wszystkich wersji danego szablonu"""
        template = self.prompts.get(template_name)
        if not template or "versions" not in template:
            return ["v1"] if template else []
        return sorted(template["versions"].keys())

    def get_default_version(self, template_name: str) -> str:
        """Zwraca domyślną wersję szablonu lub 'v1' jako bezpieczny fallback"""
        template = self.prompts.get(template_name)
        if template and "default_version" in template:
            return template["default_version"]
        
        # Jeśli nie ma default_version, ale istnieje wersja v1 – zwróć v1
        if template and "versions" in template and "v1" in template["versions"]:
            return "v1"
        
        return "v1"  # ostateczny fallback

    def get_prompt(self, template_name: str, version: str = None) -> Optional[Dict[str, Any]]:
        """
        Zwraca szablon promptu w podanej wersji.
        Jeśli wersja nie jest podana - zwraca domyślną wersję.
        """
        template = self.prompts.get(template_name)
        if not template:
            return None

        if "versions" in template and isinstance(template["versions"], dict):
            if version is None:
                version = self.get_default_version(template_name)
            return template["versions"].get(version)

        # Stara struktura bez wersjonowania
        return template

    def get_system_prompt(self, template_name: str, version: str = None) -> Optional[str]:
        """Zwraca tylko część 'system' wybranego promptu"""
        prompt = self.get_prompt(template_name, version)
        return prompt.get("system") if prompt else None

    def get_user_prompt(self, template_name: str, version: str = None) -> Optional[str]:
        """Zwraca tylko część 'user' wybranego promptu"""
        prompt = self.get_prompt(template_name, version)
        return prompt.get("user") if prompt else None

    def add_prompt(
        self,
        prompt_name: str,
        system: str,
        user: str,
        version: str = "v1"
    ) -> bool:
        """
        Dodaje nowy prompt lub nową wersję istniejącego promptu.
        Jeśli plik JSON nie istnieje – tworzy go automatycznie.
        """
        try:
            file_path = self.prompts_dir / f"{prompt_name}.json"

            if file_path.exists():
                with file_path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
            else:
                data = {"versions": {}, "default_version": version}

            if "versions" not in data or not isinstance(data["versions"], dict):
                data["versions"] = {}

            data["versions"][version] = {
                "system": system.strip(),
                "user": user.strip()
            }

            if data.get("default_version") is None:
                data["default_version"] = version

            with file_path.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            self.load_prompts()

            print(f"✓ Dodano prompt '{prompt_name}' w wersji '{version}'")
            return True

        except Exception as e:
            print(f"✗ Błąd podczas dodawania promptu '{prompt_name}': {e}")
            return False

    def build_from_template(
        self,
        prompt_name: str,
        version: str = None,
        **kwargs
    ) -> Optional[Dict[str, str]]:
        """
        Buduje prompt na podstawie szablonu i zwraca słownik z 'system' i 'user'.
        Ułatwia korzystanie przy wołaniu LLM.
        """
        template = self.get_prompt(prompt_name, version)
        if not template:
            return None

        system = template.get("system", "")
        user_template = template.get("user", "")

        try:
            user = user_template.format(**kwargs)
        except KeyError as e:
            raise ValueError(f"Brak parametru {e} w szablonie '{prompt_name}' (wersja: {version or 'domyślna'})")

        return {
            "system": system,
            "user": user
        }
    
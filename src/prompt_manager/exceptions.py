# src/prompt_manager/exceptions.py

class PromptManagerError(Exception):
    """Bazowy wyjątek dla całego modułu PromptManager."""
    pass


class PromptNotFoundError(PromptManagerError):
    """Szablon promptu o danej nazwie nie istnieje."""
    def __init__(self, name: str):
        super().__init__(f"Nie znaleziono szablonu promptu: {name}")


class InvalidPromptTemplateError(PromptManagerError):
    """Szablon promptu jest niepoprawny (brak 'system' lub 'user')."""
    def __init__(self, name: str):
        super().__init__(f"Szablon {name} jest niepoprawny – brakuje kluczy 'system' lub 'user'")


class MissingParameterError(PromptManagerError):
    """Brak wymaganego parametru przy budowaniu promptu."""
    def __init__(self, param: str, template: str):
        super().__init__(f"Brak parametru '{param}' w szablonie '{template}'")
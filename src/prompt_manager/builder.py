# src/prompt_manager/builder.py
def build_from_template(template: dict, **kwargs) -> str:
    """
    Pomocnicza funkcja – buduje prompt z szablonu i parametrów.
    Można używać niezależnie od klasy PromptManager.
    """
    system = template.get("system", "")
    user_template = template.get("user", "")

    try:
        user = user_template.format(**kwargs)
    except KeyError as e:
        raise ValueError(f"Brak parametru {e} w szablonie")

    return f"{system}\n\n{user}"
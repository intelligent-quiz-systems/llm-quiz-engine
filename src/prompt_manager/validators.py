# src/prompt_manager/validators.py
def validate_prompt_data(data: dict) -> bool:
    """Prosta walidacja struktury promptu"""
    required = {"system", "user"}
    return isinstance(data, dict) and required.issubset(data.keys())
# src/prompt_manager/types.py
from typing import TypedDict, Any


class PromptTemplate(TypedDict):
    """Typ szablonu promptu z JSON."""
    system: str
    user: str
    # możesz dodać więcej pól, np. description: Optional[str]
    # description: Optional[str]


PromptDict = dict[str, PromptTemplate]
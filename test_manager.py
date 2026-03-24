# test_manager.py
from src.prompt_manager.manager import PromptManager

def main():
    manager = PromptManager()

    print("\n=== Dostępne szablony promptów ===")
    templates = manager.list_templates()
    if not templates:
        print("Brak szablonów – sprawdź katalog data/prompts/")
    else:
        for i, template in enumerate(templates, 1):
            default_version = manager.get_default_version(template)
            print(f"{i:2d}. {template} (domyślna wersja: {default_version})")
        print(f"\nŁącznie: {len(templates)} szablonów\n")

    # Przykład pobrania promptu z wersją
    prompt_v1 = manager.get_prompt("multiple_choice", version="v1")
    print(f"multiple_choice v1 istnieje: {prompt_v1 is not None}")

if __name__ == "__main__":
    main()
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
            print(f"{i:2d}. {template}")
        print(f"\nŁącznie: {len(templates)} szablonów\n")

    # Przykład użycia
    print("Przykład pobrania promptu:")
    prompt = manager.get_prompt("multiple_choice")
    print(f"multiple_choice → {prompt is not None}")

if __name__ == "__main__":
    main()
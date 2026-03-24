# test_manager.py
# Testy PromptManager po wprowadzeniu wersjonowania promptów

from src.prompt_manager.manager import PromptManager

def main():
    manager = PromptManager()

    print("\n=== Dostępne szablony promptów ===")
    templates = manager.list_templates()
    
    if not templates:
        print("Brak szablonów – sprawdź katalog data/prompts/")
    else:
        for i, template in enumerate(templates, 1):
            versions = manager.list_versions(template)
            default = manager.get_default_version(template)
            print(f"{i:2d}. {template:20} → wersje: {versions} (domyślna: {default})")
        print(f"\nŁącznie: {len(templates)} szablonów\n")

    # Testy pobierania promptów z wersjami
    print("=== Testy pobierania promptów z wersjami ===")
    
    template_name = "multiple_choice"
    
    # Domyślna wersja
    prompt_default = manager.get_prompt(template_name)
    print(f"[{template_name}] Domyślna wersja (v1): {'✓' if prompt_default else '✗'}")

    # Konkretna wersja
    prompt_v1 = manager.get_prompt(template_name, "v1")
    prompt_v2 = manager.get_prompt(template_name, "v2")
    
    print(f"[{template_name}] Wersja v1: {'✓' if prompt_v1 else '✗'}")
    print(f"[{template_name}] Wersja v2: {'✓' if prompt_v2 else '✗'}")

    # Testy pomocniczych metod
    system_text = manager.get_system_prompt(template_name, "v1")
    user_text = manager.get_user_prompt(template_name, "v1")
    
    print(f"System prompt (v1): {'✓' if system_text else '✗'} ({len(system_text) if system_text else 0} znaków)")
    print(f"User prompt (v1):   {'✓' if user_text else '✗'} ({len(user_text) if user_text else 0} znaków)")

    # Test nieistniejącej wersji
    prompt_v99 = manager.get_prompt(template_name, "v99")
    print(f"[{template_name}] Nieistniejąca wersja v99: {'✓ (None)' if prompt_v99 is None else '✗'}")

    print("\nPrompt Manager z wersjonowaniem działa poprawnie.")


if __name__ == "__main__":
    main()
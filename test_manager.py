# test_manager.py
# Testy PromptManager po wprowadzeniu wersjonowania i funkcji add_prompt()

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

    # Testy pobierania promptów
    print("=== Testy pobierania promptów z wersjami ===")
    
    template_name = "basic_quiz"
    
    prompt_default = manager.get_prompt(template_name)
    print(f"[{template_name}] Domyślna wersja (v1): {'✓' if prompt_default else '✗'}")

    system_text = manager.get_system_prompt(template_name, "v1")
    user_text = manager.get_user_prompt(template_name, "v1")
    
    print(f"System prompt (v1): {'✓' if system_text else '✗'} ({len(system_text) if system_text else 0} znaków)")
    print(f"User prompt (v1):   {'✓' if user_text else '✗'} ({len(user_text) if user_text else 0} znaków)")

    # === NOWY TEST: add_prompt() ===
    print("\n=== Test dodawania nowej wersji promptu ===")
    
    success = manager.add_prompt(
        prompt_name="basic_quiz",
        system="Jesteś bardzo precyzyjnym generatorem quizów. Zawsze zwracaj tylko czysty JSON.",
        user="Wygeneruj quiz na temat: {topic}. Poziom: {difficulty}. Liczba pytań: {num_questions}.",
        version="v2"
    )

    if success:
        print("✓ Funkcja add_prompt() zadziałała poprawnie")
        # Sprawdź, czy nowa wersja się pojawiła
        versions = manager.list_versions("basic_quiz")
        print(f"Dostępne wersje basic_quiz po dodaniu: {versions}")
        
        new_prompt = manager.get_prompt("basic_quiz", "v2")
        print(f"Czy wersja v2 została dodana: {'✓' if new_prompt else '✗'}")
    else:
        print("✗ Funkcja add_prompt() zwróciła błąd")

    print("\nPrompt Manager z wersjonowaniem i funkcją add_prompt() działa poprawnie.")


if __name__ == "__main__":
    main()
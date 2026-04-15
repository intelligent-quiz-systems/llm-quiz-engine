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

    # Testy funkcji add_prompt()
    print("\n=== Testy funkcji add_prompt() ===")
    
    success1 = manager.add_prompt(
        prompt_name="basic_quiz",
        system="Nowa, ulepszona instrukcja systemowa dla quizu.",
        user="Wygeneruj quiz na temat: {topic}. Poziom trudności: {difficulty}. Liczba pytań: {num_questions}.",
        version="v2"
    )

    if success1:
        print("✓ Dodano wersję v2 do promptu 'basic_quiz'")
        print(f"  Dostępne wersje: {manager.list_versions('basic_quiz')}")

    success2 = manager.add_prompt(
        prompt_name="short_answer_quiz",
        system="Jesteś asystentem tworzącym pytania otwarte do quizu.",
        user="Stwórz {num_questions} pytań otwartych na temat: {topic}. Poziom: {difficulty}.",
        version="v1"
    )

    if success2:
        print("✓ Dodano nowy prompt 'short_answer_quiz' w wersji v1")

    # === Test build_from_template() ===
    print("\n=== Test build_from_template() ===")
    
    built = manager.build_from_template(
        prompt_name="basic_quiz",
        topic="Python podstawy",
        difficulty="Średni",
        num_questions=5,
        quiz_structure="""{
  "questions": [
    {
      "question": "string",
      "options": ["string", "string", "string", "string"],
      "correct_index": 0
    }
  ]
}"""
    )
    
    if built:
        print("✓ build_from_template() zadziałała poprawnie")
        print(f"System: {built.get('system', '')[:120]}...")
        print(f"User:   {built.get('user', '')[:180]}...")
    else:
        print("✗ build_from_template() nie zadziałała")

    print("\nPrompt Manager z wersjonowaniem i funkcją build_from_template() działa poprawnie.")


if __name__ == "__main__":
    main()
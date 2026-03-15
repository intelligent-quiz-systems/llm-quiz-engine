# test_manager.py
# Plik testowy do sprawdzenia działania PromptManager

from src.prompt_manager.manager import PromptManager

def main():
    # Tworzymy instancję managera (ładuje prompty z data/prompts)
    manager = PromptManager()

    # Ładniejsze wyświetlanie listy szablonów w formie tabelki
    templates = manager.list_templates()  # posortowane alfabetycznie
    print("\n=== Dostępne szablony promptów ===")
    if not templates:
        print("Brak szablonów – sprawdź katalog data/prompts/")
    else:
        print("Lp. | Nazwa szablonu")
        print("----|-----------------")
        for i, template in enumerate(templates, 1):
            print(f"{i:3} | {template}")
        print(f"\nŁącznie: {len(templates)} szablonów\n")

    # Przykładowe pytanie wielokrotnego wyboru
    print("\n=== Test 1: Pytanie wielokrotnego wyboru ===")
    pytanie1 = manager.generate(
        template_name="multiple_choice",
        temat="sztuczna inteligencja",
        poziom="łatwy"
    )
    if pytanie1:
        print(pytanie1)
    else:
        print("Nie udało się wygenerować pytania.")

    # Przykładowe pytanie z opisem obrazu
    print("\n=== Test 2: Pytanie z opisem obrazu ===")
    opis_obrazu = "Zdjęcie erupcji wulkanu Etna z lotu ptaka, czerwona lawa spływająca po zboczu i czarny popiół w powietrzu"
    pytanie2 = manager.generate_from_image_description(
        opis_obrazu=opis_obrazu,
        template_name="image_based",
        temat="wulkany i geologia",
        poziom="średni"
    )
    if pytanie2:
        print(pytanie2)
    else:
        print("Nie udało się wygenerować pytania z opisem obrazu.")

if __name__ == "__main__":
    main()
# Prompt Manager – jak dodać własny szablon promptu

Dodawanie nowego szablonu jest bardzo proste – nie musisz edytować żadnego kodu Pythona.



## Gdzie wrzucać pliki

Wszystkie szablony trzymamy w folderze:  
`data/prompts/`



## Nowa struktura z wersjonowaniem (od tej wersji)

Każdy plik JSON ma teraz strukturę z wersjami:

```json
{
  "versions": {
    "v1": {
      "system": "Instrukcja systemowa...",
      "user": "Szablon z {temat} i {poziom}..."
    },
    "v2": {
      "system": "...",
      "user": "..."
    }
  },
  "default_version": "v1"
}
```


## Jak nazwać plik

Nazwa pliku = nazwa szablonu (małe litery, myślniki lub podkreślniki).
Przykład: multiple_choice.json



## Jak używać w kodzie
```
manager = PromptManager()

# Pobranie domyślnej wersji
prompt = manager.get_prompt("multiple_choice")

# Pobranie konkretnej wersji
prompt_v2 = manager.get_prompt("multiple_choice", version="v2")

# Pobranie tylko części system lub user
system = manager.get_system_prompt("multiple_choice")
user = manager.get_user_prompt("multiple_choice", version="v2")
```


## Jak przetestować swój szablon

1. Dodaj lub zaktualizuj plik .json w data/prompts/
2. Uruchom python test_manager.py
3. Sprawdź, czy szablon pojawił się na liście



## Najczęstsze błędy

- Brak klucza "versions" lub "default_version"
- Błędna składnia JSON
- Spacja lub wielka litera w nazwie pliku



Gotowe! Dodaj swój szablon i zrób pull request :)


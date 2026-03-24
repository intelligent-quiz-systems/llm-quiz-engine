# Prompt Manager – jak dodać własny szablon promptu

Prompt Manager jest odpowiedzialny tylko za ładowanie i udostępnianie szablonów promptów.  
Komunikacja z LLM odbywa się w module `src/llm`.



## Gdzie wrzucać pliki

Wszystkie szablony trzymamy w folderze:  
`data/prompts/`



## Struktura z wersjonowaniem (aktualna)

Od tej wersji każdy plik JSON ma strukturę wspierającą wersjonowanie:

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
system = manager.get_system_prompt("multiple_choice", "v1")
user = manager.get_user_prompt("multiple_choice", "v2")

# Lista dostępnych wersji szablonu
versions = manager.list_versions("multiple_choice")
```



## Jak przetestować swój szablon

1. Dodaj lub zaktualizuj plik .json w data/prompts/
2. Uruchom python test_manager.py
3. Sprawdź, czy szablon i jego wersje pojawiają się na liście




## Najczęstsze błędy

- Brak klucza "versions" lub "default_version"
- Błędna składnia JSON
- Spacja lub wielka litera w nazwie pliku




Gotowe! Dodaj swój szablon (lub nową wersję) i zrób pull request :)




# Prompt Manager – jak zarządzać promptami

Prompt Manager służy tylko do **ładowania, wersjonowania i udostępniania promptów**.  
Komunikacja z LLM odbywa się w module `src/llm`.


## Gdzie wrzucać pliki

Wszystkie szablony promptów znajdują się w folderze:  
`data/prompts/`


## Struktura promptów z wersjonowaniem

Każdy plik JSON ma następującą strukturę:

```json
{
  "versions": {
    "v1": {
      "system": "Instrukcja systemowa...",
      "user": "Szablon pytania z {topic}..."
    },
    "v2": {
      "system": "...",
      "user": "..."
    }
  },
  "default_version": "v1"
}
```


## Jak używać
```
manager = PromptManager()

# Pobranie domyślnej wersji
prompt = manager.get_prompt("basic_quiz")

# Pobranie konkretnej wersji
prompt_v2 = manager.get_prompt("basic_quiz", version="v2")

# Pobranie tylko części system lub user
system = manager.get_system_prompt("basic_quiz", "v1")
user = manager.get_user_prompt("basic_quiz", "v2")

# Lista dostępnych wersji
versions = manager.list_versions("basic_quiz")
```


## Dodawanie nowych promptów lub wersji programistycznie
```
# Dodanie nowej wersji do istniejącego promptu
manager.add_prompt(
    prompt_name="basic_quiz",
    system="Nowa instrukcja systemowa...",
    user="Nowy szablon z {topic}...",
    version="v2"
)

# Dodanie zupełnie nowego promptu
manager.add_prompt(
    prompt_name="new_quiz_type",
    system="System prompt...",
    user="User prompt z {parametry}...",
    version="v1"
)
```


## Jak przetestować

Uruchom:
python test_manager.py


## Najczęstsze błędy

- Brak klucza "versions" lub "default_version"
- Błędna składnia JSON
- Spacja lub wielka litera w nazwie pliku

Gotowe! Dodawaj nowe prompty i wersje za pomocą add_prompt() i rób pull request :)






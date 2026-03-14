# Prompt Manager – jak dodać własny szablon promptu

Dodawanie nowego szablonu jest bardzo proste – **nie musisz edytować żadnego kodu Pythona**.


## Gdzie wrzucać pliki

Wszystkie szablony trzymamy w folderze:
`data/prompts/`


## Jak nazwać plik

Nazwa pliku = nazwa szablonu (małe litery, bez spacji, myślniki lub podkreślniki).
Przykład:  
`multiple_choice.json` → używasz go jako `manager.generate("multiple_choice", ...)`


## Wymagana struktura pliku JSON

Każdy plik **musi** mieć dokładnie dwa klucze:

```json
{
  "system": "Instrukcja systemowa dla modelu (kim jest asystent, jak ma odpowiadać)",
  "user":   "Szablon pytania z miejscami na zmienne w nawiasach klamrowych {zmienna}"
}
```


## Przykład poprawnego pliku

```json
{
  "system": "Jesteś precyzyjnym asystentem quizowym. Odpowiadaj tylko pytaniem i opcjami.",
  "user":   "Stwórz pytanie wielokrotnego wyboru na temat {temat}. Trudność: {poziom}."
}
```


## Jakie zmienne możesz używać

W polu "user" możesz wstawiać dowolne zmienne w formacie {nazwa_zmiennej}.



## Przykład użycia w kodzie 

```python
manager.generate("multiple_choice", temat="sztuczna inteligencja", poziom="łatwy")
```


Dostępne zmienne zależą od tego, co przekażesz w **kwargs.


## Jak przetestować swój szablon

1. Dodaj plik .json do data/prompts/
2. Zrób commit i push na swoją gałąź
3. Uruchom test_manager.py (lub własny skrypt)
4. Sprawdź, czy szablon pojawił się na liście: Dostępne szablony promptów: [...]


## Najczęstsze błędy:

- Brak klucza "system" lub "user" → szablon nie zostanie wczytany
- Błędna składnia JSON → komunikat w konsoli przy ładowaniu
- Spacja lub wielka litera w nazwie pliku → szablon nie zostanie rozpoznany
- Plik nie jest zapisany w UTF-8 → może pojawić się błąd dekodowania


Gotowe! Dodaj swój szablon i zrób pull request :)



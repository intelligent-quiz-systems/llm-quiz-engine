# TEMPORARY DEBUG DESCRIPTION

Dodałem na branchu `llm-debug` tymczasowe logi debugowe LLM, na razie bez PR, tylko do podglądu.

Obecnie logujemy:
- liczbę pytań żądaną przez użytkownika
- liczbę pytań zwróconych przez model
- usage tokenów
- status odpowiedzi
- informację o ucięciu odpowiedzi
- proste checki jakościowe:
  - błędy struktury
  - duplicate options
  - duplicate / similar questions

np.:

===== REQUEST INFO =====
requested_questions: 42
system_prompt_chars: 697
user_prompt_chars: 308

===== TOKEN USAGE =====
input_tokens: 508
output_tokens: 2555
total_tokens: 3063
reasoning_tokens: 230

===== RESPONSE STATUS =====
status: completed
incomplete_details: None
max_output_tokens: None
service_tier: default

===== OUTPUT SIZE =====
raw_text_chars: 8248

===== QUESTION COUNT =====
requested_questions: 42
returned_questions: 49
question_delta: 7

===== QUIZ DEBUG CHECKS =====
requested_questions: 42
structure_issues_count: 2
duplicate_questions_count: 0
similar_questions_count: 2

--- STRUCTURE ISSUES ---
Q20: duplicate options detected
Q24: duplicate options detected

--- VERY SIMILAR QUESTIONS ---
Very similar questions: Q27 and Q38 (score=0.91)
Very similar questions: Q31 and Q47 (score=0.90)

===== RAW LLM RESPONSE =====
…

## Co widać z testów

Przy większych quizach nadal potwierdza się problem z limitem odpowiedzi.  
Gdy `output_tokens` dochodzą do ok. `3072`, często pojawia się:
- `status = incomplete`
- `incomplete_details = max_output_tokens`

Wtedy skutkiem jest:
- ucięty quiz
- niepełny JSON
- albo zbyt mała liczba pytań

Dodatkowo w części testów widać, że nawet przy:
- `status = completed`

model nadal potrafi:
- zwrócić złą liczbę pytań
- wygenerować duplicate options
- wygenerować bardzo podobne pytania

Na ten moment wygląda to tak, że mamy dwa problemy:
1. limit odpowiedzi / ucięcie generacji
2. niestabilność jakości generacji przy większych quizach

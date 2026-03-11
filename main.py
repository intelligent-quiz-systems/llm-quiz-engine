from src.llm import generate_quiz

quiz = generate_quiz("Podstawy Pythona", 4)

print("Tytuł quizu:", quiz["quiz_title"])
print()

for i, q in enumerate(quiz["questions"], 1):
    print(f"Pytanie {i}: {q['question']}")
    for j, option in enumerate(q["options"]):
        print(f"{chr(65+j)}) {option}")
    print("Poprawna odpowiedź:", q["correct_index"])
    print()
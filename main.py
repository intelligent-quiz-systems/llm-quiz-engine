from src.llm import generate_quiz

topic = input("Podaj temat quizu: ")
difficulty = input("Wybierz poziom trudności (easy/medium/hard): ")
num_questions = int(input("Ile pytań wygenerować? "))

quiz = generate_quiz(topic, difficulty, num_questions)

print("\nTytuł quizu:", quiz["quiz_title"])
print()

for i, q in enumerate(quiz["questions"], 1):
    print(f"Pytanie {i}: {q['question']}")
    for j, option in enumerate(q["options"]):
        print(f"{chr(65+j)}) {option}")
    print("Poprawna odpowiedź:", q["correct_index"])
    print()
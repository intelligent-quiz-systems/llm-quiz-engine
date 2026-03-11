from src.llm import generate_quiz

topic = input("Podaj temat quizu: ")
difficulty = input("Wybierz poziom trudności (easy/medium/hard): ")
num_questions = int(input("Ile pytań wygenerować? "))

quiz = generate_quiz(topic, difficulty, num_questions)

letters = ["A", "B", "C", "D"]
score = 0
results = []

print(f"\nTytuł quizu: {quiz['quiz_title']}\n")

for i, q in enumerate(quiz["questions"], 1):
    print(f"Pytanie {i}: {q['question']}")
    for j, option in enumerate(q["options"]):
        print(f"{letters[j]}) {option}")

    user_choice = input("Twój wybór (A/B/C/D): ").strip().upper()

    while user_choice not in letters:
        user_choice = input("Podaj tylko A, B, C lub D: ").strip().upper()

    user_index = letters.index(user_choice)
    correct_index = q["correct_index"]
    is_correct = user_index == correct_index

    if is_correct:
        score += 1

    results.append({
        "question": q["question"],
        "user_choice": user_choice,
        "user_answer": q["options"][user_index],
        "correct_choice": letters[correct_index],
        "correct_answer": q["options"][correct_index],
        "is_correct": is_correct
    })

    print("✅ Dobrze!\n" if is_correct else "❌ Błędna odpowiedź.\n")

total = len(quiz["questions"])
percent = (score / total) * 100

print("\n=== PODSUMOWANIE ===")
for i, r in enumerate(results, 1):
    print(f"\nPytanie {i}: {r['question']}")
    print(f"Twoja odpowiedź: {r['user_choice']}) {r['user_answer']}")
    print(f"Poprawna odpowiedź: {r['correct_choice']}) {r['correct_answer']}")
    print("Wynik: ✅ poprawna" if r["is_correct"] else "Wynik: ❌ błędna")

print(f"\nTwój wynik: {score}/{total} ({percent:.0f}%)")
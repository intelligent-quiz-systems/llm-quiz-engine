from src.llm import generate_quiz

quiz = generate_quiz("geografia")

print("\n" + quiz["question"] + "\n")

letters = ["A", "B", "C", "D"]

for i, answer in enumerate(quiz["answers"]):
    print(f"{letters[i]}) {answer}")

user_input = input("\nTwój wybór (A/B/C/D): ").strip().upper()

# Zamiana litery na indeks
if user_input in letters:
    user_index = letters.index(user_input)

    if user_index == quiz["correct_answer"]:
        print("\n✅ Dobrze!")
    else:
        correct_letter = letters[quiz["correct_answer"]]
        print(f"\n❌ Źle! Poprawna odpowiedź to {correct_letter}.")
else:
    print("\n⚠ Niepoprawny wybór.")
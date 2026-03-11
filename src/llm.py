from groq import Groq
import os
import json

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def generate_quiz(topic: str, difficulty: str, num_questions: int):
    prompt = f"""
You are a JSON generator.

Generate a quiz in Polish about: {topic}
Difficulty level: {difficulty}
Number of questions: {num_questions}

Return ONLY valid JSON.
Do not include markdown.
Do not include explanations.
Do not include text before or after JSON.

Use exactly this structure:

{{
  "quiz_title": "{topic}",
  "questions": [
    {{
      "question": "string",
      "options": ["string", "string", "string", "string"],
      "correct_index": 0
    }}
  ]
}}

Requirements:
- generate exactly {num_questions} questions
- each question must have exactly 4 options
- correct_index must be an integer from 0 to 3
- all content must be in Polish
- difficulty must match: {difficulty}
- questions must stay strictly within the topic: {topic}
- do not expand the topic
- do not introduce subtraction, multiplication, division, powers, equations, or mixed operations unless they are explicitly part of the topic
- if the topic is simple arithmetic, generate only direct single-operation exercises
- keep questions appropriate to the declared topic and difficulty
"""

    chat_completion = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="openai/gpt-oss-120b",
        temperature=0.7,
    )

    response_text = chat_completion.choices[0].message.content

    print("\n===== RAW RESPONSE =====")
    print(repr(response_text))
    print("========================\n")

    quiz_data = json.loads(response_text)
    return quiz_data
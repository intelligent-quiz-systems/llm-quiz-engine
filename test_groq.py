from groq import Groq
import os

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

prompt = """
Wygeneruj pytanie quizowe z geografii.
Podaj:
- pytanie
- 4 odpowiedzi
- wskaż poprawną odpowiedź
"""

chat_completion = client.chat.completions.create(
    messages=[
        {"role": "user", "content": prompt}
    ],
    model="llama-3.3-70b-versatile",
)

print(chat_completion.choices[0].message.content)
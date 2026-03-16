# Obsługa wizji (end-to-end z obrazów) – wyłączona na razie (brak dostępu do modelu)
# Można włączyć po zmianie modelu / klucza API

# src/prompt_manager/vision.py
from groq import Groq
from pathlib import Path
import base64
import os
from dotenv import load_dotenv
from typing import Optional

load_dotenv()

class VisionClient:
    def __init__(self):
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("Brak GROQ_API_KEY w .env – dodaj go do pliku .env")
        self.client = Groq(api_key=api_key)

    def generate_question_from_image(
        self,
        image_path: str | Path,
        model: str = "llama-4-scout-17b-16e-instruct",  # ← Twój znaleziony model
        max_tokens: int = 512,
        temperature: float = 0.7,
        system_prompt: str = "Jesteś precyzyjnym asystentem quizowym. Na podstawie przesłanego obrazu stwórz pytanie wielokrotnego wyboru (dokładnie 4 opcje, jedna poprawna).",
        temat: str = "ogólny",
        poziom: str = "średni"
    ) -> Optional[str]:
        image_path = Path(image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"Obraz {image_path} nie istnieje")

        # Konwertujemy obraz na base64
        with open(image_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')

        try:
            response = self.client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": system_prompt
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": f"Temat: {temat}. Trudność: {poziom}. Pytanie musi być mocno związane z obrazem."
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"Błąd Groq Vision: {e}")
            return None
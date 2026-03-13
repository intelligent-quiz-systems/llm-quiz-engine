# src/prompt_manager/groq_client.py
from groq import Groq
import os
from dotenv import load_dotenv

load_dotenv()  # ładuje .env jeśli istnieje

class GroqClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("Brak klucza API Groq – ustaw GROQ_API_KEY w pliku .env")

        self.client = Groq(api_key=self.api_key)

    def generate_response(self, prompt: str, model: str = "llama3-70b-8192", max_tokens: int = 512, temperature: float = 0.7) -> Optional[str]:
        """Wysyła prosty prompt jako wiadomość użytkownika i zwraca odpowiedź."""
        try:
            response = self.client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"Błąd podczas zapytania do Groq: {e}")
            return None
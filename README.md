# LLM Quiz Generator

Simple CLI quiz generator powered by a Large Language Model (LLM).

The application connects to the Groq API using the OpenAI-compatible interface and generates quiz questions in structured JSON format.

---

# Features

- quiz generation using LLM
- structured JSON output
- interactive CLI quiz
- answer validation
- score calculation
- quiz summary

---

# Setup

## 1. Clone repository

git clone <repository_url>

## 2. Create `.env` file

Create a file named `.env` in the root directory.

Example configuration:

OPENAI_API_KEY=your_api_key_here  
OPENAI_BASE_URL=https://api.groq.com/openai/v1

You can copy the example file:

cp .env.example .env

Then paste your API key.

---

## 3. Install dependencies

pip install groq python-dotenv

---

## 4. Run the application

python main.py

---

# Example usage

The program will ask for:

- quiz topic
- difficulty level
- number of questions

Then it generates a quiz and lets the user answer questions one by one.

# Example:

Podaj temat quizu: matematyka
Wybierz poziom trudności:

- łatwy
- średni
- trudny

Ile pytań wygenerować? 3

## Project structure

quiz-cli-proba
│
├── src
│ └── llm.py # LLM integration and quiz generation
│
├── main.py # CLI quiz logic
├── .env.example # example environment configuration
├── .gitignore
└── README.md
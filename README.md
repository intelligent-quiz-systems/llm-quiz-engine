# llm-quiz-engine
AI-powered system for automated quiz generation using Large Language Models (LLMs).

## Installation and Running the Application

### 1. Install Dependencies

Before running the application, install all required Python packages:

```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Create a `.env` file in the root directory.

You can copy the example file:

```bash
cp .env.example .env
```

Then open the `.env` file and set your API key:

```
GROQ_API_KEY=your_groq_api_key_here
GROQ_BASE_URL="https://api.groq.com/openai/v1"
```

### 3. Start the Application in Browser Mode

Run the following command in the terminal:

```bash
streamlit run src/app.py
```

### 4. Open the Application

After starting, the application will be available in your browser at:

```
http://localhost:8502/
```

## Contributors

- Artur `Arturstrag`: unit tests, quiz history, RAG foundation, source chunking/batching pipeline, source processing.
- Joanna Czarnocka `joannaczarnocka`: calling LLM with Pydantic validation, UI screens in streamlit (configuration, actual quiz and summary), loading input files(txt or pdf) to context to generate quiz from them.
- Krystian Oberland `krystian-oberland`: LLM integration, retry/reduce/fallback flow, generation state & batch logs, partial loading with background worker, diagnostics & observability, quality checks & guardrails, RAG runtime integration.
- Magdalena `magbor1`: prompt manager, AI hint system, scoring details UI, hint penalties.
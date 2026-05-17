import math
import time
from urllib.parse import quote
from enum import Enum

import streamlit as st
from streamlit_autorefresh import st_autorefresh
from validations.validate_quiz import validate_quiz
from datetime import datetime, timezone
from uuid import uuid4 
from history.history import append_attempt, load_history

from llm.llm import generate_hint, generate_quiz

QUIZ_PAGE_SIZE = 3
OPTION_LABELS = ["A", "B", "C", "D", "E", "F"]
DEFAULT_QUESTION_COUNT = 10
DEFAULT_TIME_LIMIT_MINUTES = 20
DEFAULT_TOPIC = "Podstawy Pythona"
MAX_QUESTION_COUNT = 10
MAX_TIME_LIMIT_MINUTES = 60
MAX_SOURCE_FILE_SIZE_BYTES = 10 * 1024 * 1024
MIN_EXTRACTED_SOURCE_CHARS = 500


def format_size_label(size_bytes: int) -> str:
    if size_bytes % (1024 * 1024) == 0:
        return f"{size_bytes // (1024 * 1024)} MB"
    return f"{size_bytes // 1024} KB"


class QuizDifficulty(Enum):
    EASY = "Łatwy"
    MEDIUM = "Średni"
    HARD = "Trudny"

    def __str__(self):
        return self.value


DEFAULT_JSON = """{
  "quiz_title": "Podstawy Pythona",
  "questions": [
    {
      "question": "Co robi funkcja len() w Pythonie?",
      "options": [
        "Zwraca długość obiektu",
        "Usuwa element z listy",
        "Kończy działanie programu",
        "Tworzy nową funkcję"
      ],
      "correct_index": 0
    },
    {
      "question": "Jak w Pythonie tworzy się listę?",
      "options": [
        "Za pomocą {}",
        "Za pomocą []",
        "Za pomocą ()",
        "Za pomocą <>"
      ],
      "correct_index": 1
    },
    {
      "question": "Które słowo kluczowe służy do definiowania funkcji w Pythonie?",
      "options": [
        "function",
        "define",
        "def",
        "func"
      ],
      "correct_index": 2
    },
    {
      "question": "Jaki typ danych zwraca funkcja input() w Pythonie?",
      "options": [
        "int",
        "float",
        "string",
        "bool"
      ],
      "correct_index": 2
    },
    {
      "question": "Jak zaczyna się komentarz w Pythonie?",
      "options": [
        "//",
        "#",
        "/*",
        "--"
      ],
      "correct_index": 1
    }
  ]
}"""


def init_state():
    defaults = {
        "app_step": "config",
        "quiz_data": None,
        "current_page": 0,
        "quiz_deadline": None,
        "answers": {},
        "timeout_happened": False,
        "config": None,
        "quiz_started_at": None,
        "history_saved": False,
        "topic_input": DEFAULT_TOPIC,
        "pending_topic_input": None,
        "source_topic_file_id": None,
        "quiz_source_mode": "Temat quizu",
        "prev_quiz_source_mode": "Temat quizu",
        "source_uploader_version": 0,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def inject_css():
    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 1rem;
        }

        h1 {
            font-size: 1.9rem !important;
            margin-bottom: 0.4rem !important;
        }

        h3 {
            font-size: 1.15rem !important;
            margin-bottom: 0.3rem !important;
        }

        .question-card {
            border: 1px solid #e6e6e6;
            padding: 14px;
            border-radius: 10px;
            margin-bottom: 14px;
            background: white;
        }

        .option-card {
            border: 1px solid #e6e6e6;
            padding: 10px;
            border-radius: 8px;
            margin-bottom: 8px;
        }

        .correct {
            background: #eaf8ee;
            border: 1px solid #7acb8c;
        }

        .wrong {
            background: #fdecec;
            border: 1px solid #e58f8f;
        }

        .info-option {
            background: #eaf2ff;
            border: 1px solid #7ea6ff;
        }

        .option-note {
            margin-top: 4px;
            font-size: 0.9rem;
            color: #555;
            font-style: italic;
        }

        .option-line {
            display: flex;
            align-items: center;
            gap: 8px;
            font-weight: 600;
        }

        .option-icon {
            width: 20px;
            display: inline-block;
            text-align: center;
        }

        /* Hide Streamlit default helper text under file uploader */
        [data-testid="stFileUploader"] small {
            display: none !important;
        }
        [data-testid="stFileUploader"] [data-testid="stFileUploaderDropzoneInstructions"] > div:last-child {
            display: none !important;
        }
        [data-testid="stFileUploader"] [data-testid="stFileUploaderDropzoneInstructions"] p:last-child {
            display: none !important;
        }

        /* Replace default uploader button text with Polish label */
        [data-testid="stFileUploader"] button div[data-testid="stMarkdownContainer"] p {
            visibility: hidden;
            position: relative;
        }

        [data-testid="stFileUploader"] button div[data-testid="stMarkdownContainer"] p::after {
            content: "Załaduj";
            visibility: visible;
            position: absolute;
            left: 0;
            top: 0;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def inject_browser_scroll_on_nav():
    html_doc = """
    <!doctype html>
    <html>
      <body>
        <script>
          (function () {
              const parentDoc = window.parent.document;

              function forceTopScroll() {
                  const win = window.parent;

                  try {
                      win.scrollTo({ top: 0, left: 0, behavior: "auto" });
                  } catch (e) {}

                  const selectors = [
                      '[data-testid="stAppViewContainer"]',
                      '[data-testid="stMain"]',
                      'section.main',
                      '.main',
                      'body',
                      'html'
                  ];

                  selectors.forEach((selector) => {
                      const el = parentDoc.querySelector(selector);
                      if (el) {
                          try {
                              el.scrollTop = 0;
                              el.scrollTo({ top: 0, left: 0, behavior: "auto" });
                          } catch (e) {}
                      }
                  });

                  if (parentDoc.documentElement) {
                      parentDoc.documentElement.scrollTop = 0;
                  }

                  if (parentDoc.body) {
                      parentDoc.body.scrollTop = 0;
                  }
              }

              function bindScroll(buttonText) {
                  const buttons = Array.from(parentDoc.querySelectorAll("button"));
                  const target = buttons.find((btn) => {
                      const text = (btn.innerText || btn.textContent || "").trim();
                      return text === buttonText;
                  });

                  if (!target) return;
                  if (target.dataset.scrollBound === "1") return;

                  target.dataset.scrollBound = "1";

                  target.addEventListener(
                      "click",
                      function () {
                          forceTopScroll();
                          requestAnimationFrame(forceTopScroll);
                          setTimeout(forceTopScroll, 0);
                          setTimeout(forceTopScroll, 20);
                          setTimeout(forceTopScroll, 60);
                          setTimeout(forceTopScroll, 120);
                      },
                      true
                  );
              }

              function bindAll() {
                  [
                      "Dalej",
                      "Wstecz",
                      "Zakończ quiz",
                      "Resetuj quiz",
                      "Nowy quiz",
                      "Generuj quiz"
                  ].forEach(bindScroll);
              }

              bindAll();
              setTimeout(bindAll, 150);
              setTimeout(bindAll, 400);
              setTimeout(bindAll, 800);
          })();
        </script>
      </body>
    </html>
    """

    st.iframe(
        src=f"data:text/html;charset=utf-8,{quote(html_doc)}",
        height=1,
    )


def difficulty_label(value):
    if isinstance(value, QuizDifficulty):
        return value.value
    return str(value) if value is not None else "—"


def render_config_screen():
    st.title("Generator quizu")

    pending_topic = st.session_state.get("pending_topic_input")
    if pending_topic:
        st.session_state.topic_input = pending_topic
        st.session_state.pending_topic_input = None

    source_mode = st.radio(
        "Źródło quizu",
        options=["Temat quizu", "Plik"],
        key="quiz_source_mode",
        horizontal=True,
    )

    previous_mode = st.session_state.get("prev_quiz_source_mode")
    if previous_mode != source_mode:
        if source_mode == "Temat quizu":
            # file_uploader cannot be cleared by direct assignment;
            # bumping key forces a fresh, empty uploader instance.
            st.session_state.source_uploader_version += 1
        st.session_state.prev_quiz_source_mode = source_mode
        st.rerun()

    source_file = None
    if source_mode == "Plik":
        source_file = st.file_uploader(
            f"Plik źródłowy (.txt lub .pdf, max {format_size_label(MAX_SOURCE_FILE_SIZE_BYTES)})",
            type=["txt", "pdf"],
            help="Po załadowaniu pliku temat quizu zostanie wykryty automatycznie przez LLM.",
            key=f"source_file_input_{st.session_state.source_uploader_version}",
        )

        if source_file is not None and source_file.size > MAX_SOURCE_FILE_SIZE_BYTES:
            st.error(
                f"Plik jest za duży. Maksymalny rozmiar to {format_size_label(MAX_SOURCE_FILE_SIZE_BYTES)}."
            )

    topic = st.text_input("Temat quizu", key="topic_input")
    question_count = st.number_input(
        "Liczba pytań",
        min_value=1,
        max_value=MAX_QUESTION_COUNT,
        value=DEFAULT_QUESTION_COUNT,
        step=1,
    )
    difficulty = st.selectbox(
        "Poziom trudności",
        options=list(QuizDifficulty),
        format_func=lambda x: x.value,
        index=1,
    )
    time_limit = st.number_input(
        "Limit czasu (minuty)",
        min_value=1,
        max_value=MAX_TIME_LIMIT_MINUTES,
        value=DEFAULT_TIME_LIMIT_MINUTES,
        step=1,
    )

    submitted = st.button("Generuj quiz", type="primary")

    inject_browser_scroll_on_nav()
    render_history_preview()

    return {
        "submitted": submitted,
        "source_mode": source_mode,
        "source_file": source_file,
        "topic": topic,
        "question_count": int(question_count),
        "difficulty": difficulty,
        "time_limit": int(time_limit),
    }


def start_timer(minutes: int):
    if st.session_state.quiz_deadline is None:
        st.session_state.quiz_deadline = time.time() + int(minutes) * 60
        st.session_state.timeout_happened = False


def remaining_time():
    deadline = st.session_state.quiz_deadline
    if deadline is None:
        return None

    remaining = math.ceil(deadline - time.time())
    return max(0, remaining)


def count_answered_questions(quiz):
    questions = quiz.get("questions", [])
    return sum(1 for i in range(len(questions)) if st.session_state.answers.get(i) is not None)


def _prepare_widget_value(question_index: int):
    widget_key = f"widget_q_{question_index}"
    saved_value = st.session_state.answers.get(question_index)
    if widget_key not in st.session_state:
        st.session_state[widget_key] = saved_value


def _persist_widget_value(question_index: int):
    widget_key = f"widget_q_{question_index}"
    st.session_state.answers[question_index] = st.session_state.get(widget_key)


def format_option_with_letter(options, option_value):
    option_index = options.index(option_value)
    return f"{OPTION_LABELS[option_index]}. {option_value}"


def reset_quiz_state():
    """Resetuje cały stan quizu, w tym hinty i punktację."""
    st.session_state.quiz_deadline = None
    st.session_state.answers = {}
    st.session_state.current_page = 0
    st.session_state.timeout_happened = False
    st.session_state.quiz_started_at = None
    st.session_state.history_saved = False
    
    # Ważne: czyszczenie hintów
    st.session_state.hint_usage = {}
    st.session_state.shown_hints = {}

    # Usuwanie widget keys
    keys_to_remove = [k for k in st.session_state.keys() if k.startswith("widget_q_")]
    for key in keys_to_remove:
        if key in st.session_state:
            del st.session_state[key]


def render_sidebar_timer():
    if st.session_state.app_step != "quiz":
        return

    remaining = remaining_time()
    if remaining is None:
        return

    minutes = remaining // 60
    seconds = remaining % 60

    st.subheader("⏱ Pozostały czas")
    if remaining <= 30:
        st.error(f"{minutes:02d}:{seconds:02d}")
    else:
        st.info(f"{minutes:02d}:{seconds:02d}")

    if remaining <= 0:
        st.session_state.timeout_happened = True
        st.session_state.app_step = "results"
        st.rerun()


def render_sidebar_status(quiz, config):
    questions = quiz.get("questions", [])
    total_questions = len(questions)
    answered = count_answered_questions(quiz)
    progress = answered / total_questions if total_questions > 0 else 0.0
    total_pages = math.ceil(total_questions / QUIZ_PAGE_SIZE) if total_questions > 0 else 1

    with st.sidebar:
        st.header(quiz.get("topic") or quiz.get("quiz_title", "Quiz"))
        st.progress(progress, text=f"Postęp: {answered}/{total_questions}")
        st.write(f"**Strona:** {st.session_state.current_page + 1}/{total_pages}")
        st.write(f"**Trudność:** {difficulty_label(config.get('difficulty'))}")
        st.write(f"**Limit czasu:** {config.get('time_limit', DEFAULT_TIME_LIMIT_MINUTES)} min")
        render_sidebar_timer()


def render_quiz_screen(quiz, config):
    st_autorefresh(interval=1000, key="quiz_timer")

    is_valid, error_message = validate_quiz(quiz)
    if not is_valid:
        st.error(f"Niepoprawny format quizu: {error_message}")
        st.stop()

    start_timer(config.get("time_limit", DEFAULT_TIME_LIMIT_MINUTES))

    questions = quiz["questions"]
    render_sidebar_status(quiz, config)

    st.title(quiz.get("quiz_title", quiz.get("topic", "Quiz")))

    # === ZASADY PUNKTOWANIA ===
    with st.expander("📋 Zasady punktacji", expanded=True):
        st.markdown("""
        - Poprawna odpowiedź: **+1 punkt**
        - Niepoprawna odpowiedź: **0 punktów**
        - Każda podpowiedź: **-0.5 punktu**
        """)

    # Inicjalizacja stanu hintów
    if "hint_usage" not in st.session_state:
        st.session_state.hint_usage = {}
    if "shown_hints" not in st.session_state:
        st.session_state.shown_hints = {}

    total_pages = math.ceil(len(questions) / QUIZ_PAGE_SIZE)
    page = st.session_state.current_page

    start = page * QUIZ_PAGE_SIZE
    end = min(start + QUIZ_PAGE_SIZE, len(questions))

    for i in range(start, end):
        q_index = i
        q = questions[i]

        _prepare_widget_value(q_index)

        st.markdown("<div class='question-card'>", unsafe_allow_html=True)
        st.markdown(f"### Pytanie {q_index + 1}")
        st.write(q["question"])

        # === Przycisk Podpowiedź ===
        used_hints = st.session_state.hint_usage.get(q_index, 0)
        remaining = 3 - used_hints

        if used_hints < 3:
            if st.button(
                "🧠 Podpowiedź", 
                key=f"hint_btn_{q_index}",
                use_container_width=False,
                type="secondary"
            ):
                with st.spinner("Generowanie podpowiedzi..."):
                    hint_levels = ["easy", "medium", "strong"]
                    hint_level = hint_levels[used_hints]
                    
                    context = None
                    hint_text = generate_hint(
                        question=q["question"],
                        options=q["options"],
                        correct_answer=q["options"][q["correct_index"]],
                        context=context,
                        hint_level=hint_level
                    )

                    if hint_text:
                        if q_index not in st.session_state.shown_hints:
                            st.session_state.shown_hints[q_index] = []
                        
                        st.session_state.shown_hints[q_index].append({
                            "level": hint_level,
                            "text": hint_text
                        })
                        st.session_state.hint_usage[q_index] = used_hints + 1
                        
                        st.rerun()   # force odświeżenie

        st.caption(f"**{remaining}** podpowiedzi pozostałe")

        # Wyświetlanie hintów
        if q_index in st.session_state.shown_hints and st.session_state.shown_hints[q_index]:
            for idx, hint in enumerate(st.session_state.shown_hints[q_index], 1):
                level_name = {"easy": "Łatwa", "medium": "Średnia", "strong": "Mocna"}[hint["level"]]
                st.info(f"**Podpowiedź {idx} ({level_name}):** {hint['text']}")


        # Opcje odpowiedzi
        st.radio(
            f"Odpowiedź dla pytania {q_index + 1}",
            q["options"],
            key=f"widget_q_{q_index}",
            format_func=lambda x, opts=q["options"]: format_option_with_letter(opts, x),
            on_change=_persist_widget_value,
            args=(q_index,),
            label_visibility="collapsed",
        )

        _persist_widget_value(q_index)
        st.markdown("</div>", unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("Wstecz", disabled=(page == 0)):
            st.session_state.current_page -= 1
            st.rerun()

    with col2:
        if st.button("Dalej", disabled=(page >= total_pages - 1)):
            st.session_state.current_page += 1
            st.rerun()

    with col3:
        if st.button("Zakończ quiz", type="primary"):
            st.session_state.app_step = "results"
            st.rerun()

    inject_browser_scroll_on_nav()


def calculate_score(quiz):
    """
    Oblicza wynik uwzględniając zużyte podpowiedzi.
    +1 za poprawną odpowiedź
    -0.5 za każdą podpowiedź
    Minimalny wynik za pytanie = 0
    """
    total_score = 0.0

    for i, q in enumerate(quiz["questions"]):
        correct = q["options"][q["correct_index"]]
        answer = st.session_state.answers.get(i)

        # Punkty za poprawną odpowiedź
        question_score = 1.0 if answer == correct else 0.0

        # Kara za użyte podpowiedzi
        used_hints = st.session_state.hint_usage.get(i, 0)
        hint_penalty = used_hints * 0.5

        # Końcowy wynik za pytanie (nie schodzi poniżej 0)
        final_question_score = max(0.0, question_score - hint_penalty)

        total_score += final_question_score

    return total_score

def build_history_entry(quiz, config, score):
    total = len(quiz.get("questions", []))
    answered = count_answered_questions(quiz)
    started_at = st.session_state.quiz_started_at or time.time()
    finished_at = time.time()
    duration_seconds = max(0, int(finished_at - started_at))

    return {
        "attempt_id": str(uuid4()),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "topic": quiz.get("topic") or quiz.get("quiz_title", "Quiz"),
        "difficulty": difficulty_label(config.get("difficulty")),
        "question_count": total,
        "answered_count": answered,
        "score": score,
        "max_score": total,
        "percent": round((score / total) * 100, 2) if total > 0 else 0.0,
        "time_limit_minutes": config.get("time_limit", DEFAULT_TIME_LIMIT_MINUTES),
        "duration_seconds": duration_seconds,
        "timed_out": bool(st.session_state.timeout_happened),
    }

def render_results_screen(quiz, config):
    is_valid, error_message = validate_quiz(quiz)
    if not is_valid:
        st.error(f"Niepoprawny format quizu: {error_message}")
        st.stop()

    st.title("Wyniki quizu")

    score = calculate_score(quiz)
    total = len(quiz["questions"])

    # Zapisz do historii (jeśli jeszcze nie zapisano)
    if not st.session_state.history_saved:
        append_attempt(build_history_entry(quiz, config, score))
        st.session_state.history_saved = True 

    # === LEWA KOLUMNA - SZCZEGÓŁOWA PUNKTACJA ===
    with st.sidebar:
        st.header("Wyniki")
        
        correct_answers = sum(1 for i, q in enumerate(quiz["questions"]) 
                            if st.session_state.answers.get(i) == q["options"][q["correct_index"]])
        
        total_hints_used = sum(st.session_state.hint_usage.get(i, 0) for i in range(total))
        hint_penalty = total_hints_used * 0.5

        st.progress(score / total if total > 0 else 0.0, 
                   text=f"**{score:.1f} / {total}**")

        st.write("**Szczegóły punktacji:**")
        st.write(f"✅ Poprawne odpowiedzi: **{correct_answers}** × 1 pkt = **{correct_answers} pkt**")
        st.write(f"❌ Niepoprawne odpowiedzi: **{total - correct_answers}** × 0 pkt = **0 pkt**")
        st.write(f"🧠 Zużyte podpowiedzi: **{total_hints_used}** × -0.5 pkt = **-{hint_penalty:.1f} pkt**")

        st.divider()
        
        st.write(f"**Temat:** {quiz.get('topic') or quiz.get('quiz_title', 'Quiz')}")
        st.write(f"**Trudność:** {difficulty_label(config.get('difficulty'))}")
        st.write(f"**Limit czasu:** {config.get('time_limit', DEFAULT_TIME_LIMIT_MINUTES)} min")        
        
        st.divider()

    # === GŁÓWNA CZĘŚĆ - WYNIKI PYTAŃ ===
    if st.session_state.timeout_happened:
        st.warning("Czas minął. Quiz został zakończony automatycznie.")

    for i, q in enumerate(quiz["questions"]):
        correct = q["options"][q["correct_index"]]
        answer = st.session_state.answers.get(i)
        user_answered = answer is not None

        st.markdown("<div class='question-card'>", unsafe_allow_html=True)
        st.markdown(f"### Pytanie {i + 1}")
        st.write(q["question"])

        for idx, opt in enumerate(q["options"]):
            css = "option-card"
            note = ""
            icon = ""

            if opt == correct and opt == answer:
                css += " correct"
                icon = "✅"
                note = "Twoja poprawna odpowiedź"
            elif opt == correct and user_answered:
                css += " correct"
                icon = "✅"
                note = "Poprawna odpowiedź"
            elif opt == correct and not user_answered:
                css += " info-option"
                icon = "ℹ️"
                note = "Poprawna odpowiedź - brak Twojej odpowiedzi"
            elif opt == answer:
                css += " wrong"
                icon = "❌"
                note = "Twoja niepoprawna odpowiedź"

            option_text = f"{OPTION_LABELS[idx]}. {opt}"
            note_html = f"<div class='option-note'>{note}</div>" if note else ""

            st.markdown(
                f"""
                <div class='{css}'>
                    <div class='option-line'>
                        <span class='option-icon'>{icon}</span>
                        <span>{option_text}</span>
                    </div>
                    {note_html}
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown("</div>", unsafe_allow_html=True)

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Resetuj quiz"):
            reset_quiz_state()
            st.session_state.app_step = "quiz"
            st.rerun()

    with col2:
        if st.button("Nowy quiz"):
            reset_quiz_state()
            st.session_state.app_step = "config"
            st.rerun()

    inject_browser_scroll_on_nav()

def render_history_preview():
    history = load_history()

    if not history:
        return

    st.subheader("Ostatnie wyniki")

    for entry in history[:5]:
        st.write(
            f"{entry['topic']} | {entry['score']}/{entry['max_score']} "
            f"({entry['percent']}%) | {entry['difficulty']} | "
            f"{entry['finished_at'][:19].replace('T', ' ')}"
        )
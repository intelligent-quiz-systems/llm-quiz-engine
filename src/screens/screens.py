import math
import time
from enum import Enum

import streamlit as st
import streamlit.components.v1 as components
from streamlit_autorefresh import st_autorefresh
from validations.validate_quiz import validate_quiz
from datetime import datetime, timezone
from uuid import uuid4 
from history.history import append_attempt, load_history

QUIZ_PAGE_SIZE = 3
OPTION_LABELS = ["A", "B", "C", "D", "E", "F"]
DEFAULT_QUESTION_COUNT = 5
DEFAULT_TIME_LIMIT_MINUTES = 10
DEFAULT_TOPIC = "Podstawy Pythona"
MAX_QUESTION_COUNT = 20
MAX_TIME_LIMIT_MINUTES = 120


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
        "history_saved": False
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
        </style>
        """,
        unsafe_allow_html=True,
    )


def inject_browser_scroll_on_nav():
    components.html(
        """
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
        """,
        height=0,
    )


def difficulty_label(value):
    if isinstance(value, QuizDifficulty):
        return value.value
    return str(value) if value is not None else "—"


def render_config_screen():
    st.title("Generator quizu")

    topic = st.text_input("Temat quizu", DEFAULT_TOPIC)
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
    st.session_state.quiz_deadline = None
    st.session_state.answers = {}
    st.session_state.current_page = 0
    st.session_state.timeout_happened = False
    st.session_state.quiz_started_at = None
    st.session_state.history_saved = False


    keys_to_remove = [k for k in st.session_state.keys() if k.startswith("widget_q_")]
    for key in keys_to_remove:
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

    total_pages = math.ceil(len(questions) / QUIZ_PAGE_SIZE)
    page = st.session_state.current_page

    start = page * QUIZ_PAGE_SIZE
    end = min(start + QUIZ_PAGE_SIZE, len(questions))

    for i in range(start, end):
        q = questions[i]

        _prepare_widget_value(i)

        st.markdown("<div class='question-card'>", unsafe_allow_html=True)
        st.markdown(f"### Pytanie {i + 1}")
        st.write(q["question"])

        st.radio(
            f"Odpowiedź dla pytania {i + 1}",
            q["options"],
            key=f"widget_q_{i}",
            format_func=lambda x, opts=q["options"]: format_option_with_letter(opts, x),
            on_change=_persist_widget_value,
            args=(i,),
            label_visibility="collapsed",
        )

        _persist_widget_value(i)
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
    score = 0

    for i, q in enumerate(quiz["questions"]):
        correct = q["options"][q["correct_index"]]
        answer = st.session_state.answers.get(i)

        if answer == correct:
            score += 1

    return score

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

    if not st.session_state.history_saved:
        append_attempt(build_history_entry(quiz, config, score))
        st.session_state.history_saved = True 

    with st.sidebar:
        st.header("Wyniki")
        st.progress(score / total if total > 0 else 0.0, text=f"Poprawne: {score}/{total}")
        st.write(f"**Temat:** {quiz.get('topic') or quiz.get('quiz_title', 'Quiz')}")
        st.write(f"**Trudność:** {difficulty_label(config.get('difficulty'))}")
        st.write(f"**Limit czasu:** {config.get('time_limit', DEFAULT_TIME_LIMIT_MINUTES)} min")

    if st.session_state.timeout_happened:
        st.warning("Czas minął. Quiz został zakończony automatycznie.")

    st.success(f"Wynik: {score}/{total}")

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
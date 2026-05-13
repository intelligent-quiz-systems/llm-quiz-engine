import hashlib
from io import BytesIO

from pypdf import PdfReader

from screens.screens import (
    MAX_SOURCE_FILE_SIZE_BYTES,
    MIN_EXTRACTED_SOURCE_CHARS,
    format_size_label,
)


def read_uploaded_source_file(uploaded_file):
    if uploaded_file is None:
        return None, None

    if uploaded_file.size > MAX_SOURCE_FILE_SIZE_BYTES:
        return (
            None,
            f"Plik jest za duży. Maksymalny rozmiar to {format_size_label(MAX_SOURCE_FILE_SIZE_BYTES)}.",
        )

    file_name = uploaded_file.name.lower()
    file_bytes = uploaded_file.getvalue()

    if file_name.endswith(".txt"):
        try:
            source_text = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            source_text = file_bytes.decode("utf-8", errors="ignore")
    elif file_name.endswith(".pdf"):
        try:
            reader = PdfReader(BytesIO(file_bytes))
            source_text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
        except Exception:
            return None, "Nie udało się odczytać pliku PDF."
    else:
        return None, "Dozwolone są tylko pliki .txt oraz .pdf."

    stripped = source_text.strip() if source_text else ""
    if not stripped:
        return None, "Plik nie zawiera możliwego do odczytu tekstu."

    if len(stripped) < MIN_EXTRACTED_SOURCE_CHARS:
        return (
            None,
            f"Za mało tekstu po wczytaniu z pliku. Wymagane minimum {MIN_EXTRACTED_SOURCE_CHARS} znaków, "
            f"uzyskano {len(stripped)}.",
        )

    return stripped, None


def get_uploaded_file_id(uploaded_file):
    if uploaded_file is None:
        return None
    payload = uploaded_file.getvalue()
    return hashlib.sha256(payload).hexdigest()

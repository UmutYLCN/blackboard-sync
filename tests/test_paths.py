import unicodedata
from pathlib import Path

from blackboard_sync.paths import (
    NUMBER_SUFFIX_ROOM,
    WINDOWS_MAX_NAME_CHARS,
    WINDOWS_MAX_PATH,
    course_code_and_title,
    course_folder_name,
    fit_windows_path,
    note_name,
    numbered_variant,
    sanitize_name,
    split_ext,
    truncate_name,
)


def test_sanitize_keeps_ordinary_names():
    name = "CSE303_Algorithm_Analysis_for_Computer_Engineering_Syllabus_v1.pdf"
    assert sanitize_name(name) == name
    assert sanitize_name("Week 1") == "Week 1"
    assert sanitize_name("Olasılık ve İstatistik (Ödev 2).docx") == "Olasılık ve İstatistik (Ödev 2).docx"


def test_sanitize_replaces_path_separators_and_colons():
    assert sanitize_name("Lab 1/2: Sorting") == "Lab 1-2 - Sorting"


def test_sanitize_strips_control_chars_whitespace_and_hidden_prefix():
    assert sanitize_name("  Notes\t\n  final  ") == "Notes final"
    assert sanitize_name(".hidden") == "hidden"
    assert sanitize_name("trailing dots...") == "trailing dots"
    assert sanitize_name("bell\x07char") == "bell char"


def test_sanitize_fallbacks_and_entities():
    assert sanitize_name("") == "untitled"
    assert sanitize_name("..") == "untitled"
    assert sanitize_name(None) == "untitled"
    assert sanitize_name("Q&amp;A") == "Q&A"


def test_sanitize_normalizes_to_nfc():
    decomposed = unicodedata.normalize("NFD", "Güz")
    assert sanitize_name(decomposed) == unicodedata.normalize("NFC", "Güz")


def test_truncate_respects_bytes_and_keeps_extension():
    long_name = "ş" * 300 + ".pdf"
    out = truncate_name(long_name)
    assert out.endswith(".pdf")
    assert len(out.encode("utf-8")) <= 255
    assert sanitize_name(long_name, windows=False) == out


def test_split_ext():
    assert split_ext("report.final.pdf") == ("report.final", ".pdf")
    assert split_ext("README") == ("README", "")
    assert split_ext("Week 1. Intro to sets") == ("Week 1. Intro to sets", "")


def test_numbered_variant():
    assert numbered_variant("Week 1/notes.pdf", 2) == "Week 1/notes (2).pdf"
    assert numbered_variant("Week 1/README", 3) == "Week 1/README (3)"


def test_note_name():
    assert note_name("Course Website: Visualizations") == "Course Website - Visualizations.md"


def test_course_code_from_course_id_when_name_has_none():
    assert course_code_and_title("CSE303-1", "Algorithm Analysis") == ("CSE303", "Algorithm Analysis")
    assert course_folder_name("CSE303-1", "Algorithm Analysis") == "CSE303 Algorithm Analysis"


def test_course_code_from_name_prefix():
    assert course_code_and_title("_x", "MTH201-1 Linear Algebra") == ("MTH201", "Linear Algebra")
    assert course_folder_name("MTH201-1", "MTH201-1 Linear Algebra") == "MTH201 Linear Algebra"
    assert course_folder_name("COE309-1", "COE309 - Internship I") == "COE309 Internship I"


def test_course_code_without_recognizable_code():
    assert course_folder_name("ORIENT", "Student Orientation") == "ORIENT Student Orientation"


# -- Windows rules (applied only on Windows; injected here) -------------------

def test_windows_replaces_forbidden_characters():
    assert sanitize_name('Q1 "Big-O" <draft> a|b back\\slash?*', windows=True) == "Q1 'Big-O' (draft) a-b back-slash"
    assert sanitize_name("What is a heap?", windows=True) == "What is a heap"
    assert sanitize_name("???", windows=True) == "untitled"


def test_windows_rules_do_not_rename_macos_files():
    for name in ('Q1 "Big-O" <draft>', "What is a heap?", "CON", "nul.txt", "x" * 200 + ".pdf"):
        assert sanitize_name(name, windows=False) == name


def test_windows_reserved_device_names():
    assert sanitize_name("CON", windows=True) == "CON_"
    assert sanitize_name("nul.txt", windows=True) == "nul_.txt"
    assert sanitize_name("com1.tar.gz", windows=True) == "com1_.tar.gz"
    assert sanitize_name("LPT9", windows=True) == "LPT9_"
    assert sanitize_name("Console notes.pdf", windows=True) == "Console notes.pdf"
    assert sanitize_name("CON.", windows=True) == "CON_"  # trailing dot dropped first


def test_windows_trailing_dots_and_spaces():
    assert sanitize_name("Week 1 . ", windows=True) == "Week 1"


def test_windows_names_are_kept_short():
    out = sanitize_name("a" * 300 + ".pdf", windows=True)
    assert len(out) == WINDOWS_MAX_NAME_CHARS and out.endswith(".pdf")
    assert len(note_name("b" * 300, windows=True)) == WINDOWS_MAX_NAME_CHARS
    variant = numbered_variant("Week 1/" + "c" * 116 + ".pdf", 12, windows=True)
    assert variant.endswith(" (12).pdf") and len(variant.split("/")[-1]) <= WINDOWS_MAX_NAME_CHARS


def test_fit_windows_path_shortens_only_the_file_name():
    base = Path("C:/Users/student/Documents/Okul")
    short = "2026 Güz/CSE303/notes.pdf"
    assert fit_windows_path(base, short) == short
    folder = "2026-2027 Güz/" + "F" * 100
    rel = folder + "/" + "n" * 110 + ".pdf"
    fitted = fit_windows_path(base, rel)
    assert fitted.startswith(folder + "/") and fitted.endswith(".pdf")
    assert len(str(base)) + 1 + len(fitted) == WINDOWS_MAX_PATH - NUMBER_SUFFIX_ROOM
    # A folder that is already too deep keeps a readable stem instead of none.
    deep = fit_windows_path(base, "D" * 240 + "/" + "x" * 50 + ".pdf")
    assert deep.endswith("/xxxxxxxx.pdf")

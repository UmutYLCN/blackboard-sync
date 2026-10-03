import unicodedata

from blackboard_sync.paths import (
    course_code_and_title,
    course_folder_name,
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
    assert sanitize_name(long_name) == out


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

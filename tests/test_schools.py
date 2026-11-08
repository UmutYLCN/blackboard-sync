"""Known schools: a typed name, abbreviation or web domain becomes the Blackboard address."""

import argparse
import importlib.util
import re
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from blackboard_sync import schools
from blackboard_sync.cli import make_config
from blackboard_sync.settings import SettingsError, normalize_base_url

ROOT = Path(__file__).resolve().parents[1]
KSU = "https://lms.ksu.edu.sa"
ISTUN = "https://blackboard.istun.edu.tr"


def test_every_school_is_a_plain_https_address_under_its_own_domain():
    for school in schools.SCHOOLS:
        parts = urlsplit(school.url)
        assert parts.scheme == "https" and parts.path == "" and not parts.query, school.name
        assert parts.hostname == school.domain or parts.hostname.endswith("." + school.domain), school.name
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", school.verified), f"{school.name} needs the day it was checked"
        assert re.fullmatch(r"[A-Z]{2}", school.country), school.name


def test_no_name_belongs_to_two_schools():
    owner: dict[str, str] = {}
    for school in schools.SCHOOLS:
        for key in (school.name, *school.local_names, *school.aliases, school.domain):
            folded = schools.fold(key)
            assert owner.setdefault(folded, school.name) == school.name, f"{key!r} is used twice"


@pytest.mark.parametrize(
    "typed, expected",
    [
        ("King Saud University", KSU),
        ("  king   SAUD university ", KSU),
        ("KSU", KSU),
        ("ksu.edu.sa", KSU),
        ("lms.ksu.edu.sa", KSU),
        ("جامعة الملك سعود", KSU),
        ("جامعه الملك سعود", KSU),  # ة typed as ه
        ("جامعة أم القرى", "https://lms.uqu.edu.sa"),
        ("جامعه ام القرى", "https://lms.uqu.edu.sa"),  # hamza left out
        ("İstanbul Sağlık ve Teknoloji Üniversitesi", ISTUN),
        ("istanbul saglik ve teknoloji universitesi", ISTUN),
        ("ISTUN", ISTUN),
        ("KFUPM", "https://blackboard.kfupm.edu.sa"),
    ],
)
def test_a_school_is_found_by_name_abbreviation_or_domain(typed, expected):
    assert schools.resolve(typed) == expected
    assert normalize_base_url(typed) == expected


@pytest.mark.parametrize("typed", ["", "   ", "King", "Unknown University", "https://lms.ksu.edu.sa", "blackboard.school.edu"])
def test_other_text_names_no_school(typed):
    assert schools.resolve(typed) is None


def test_addresses_are_still_reduced_to_the_https_host():
    assert normalize_base_url("blackboard.okul.edu.tr") == "https://blackboard.okul.edu.tr"
    assert normalize_base_url("https://lms.ksu.edu.sa/ultra/course") == KSU
    with pytest.raises(SettingsError, match="https://"):
        normalize_base_url("http://blackboard.istun.edu.tr")  # an address with another scheme is not a school name


def test_the_command_line_accepts_a_school_name_too(tmp_path):
    args = argparse.Namespace(base_url="King Saud University", data_dir=tmp_path, dest=None)
    assert make_config(args).base_url == KSU
    args = argparse.Namespace(base_url="https://blackboard.okul.edu.tr/", data_dir=tmp_path, dest=None)
    assert make_config(args).base_url == "https://blackboard.okul.edu.tr"


def test_suggestions_list_each_school_once_by_its_english_name():
    offered = schools.suggestions()
    assert offered == [school.name for school in schools.SCHOOLS]  # same order as SCHOOLS
    assert len(offered) == len(schools.SCHOOLS) and len(offered) == len(set(offered))
    for school in schools.SCHOOLS:
        assert offered.count(school.name) == 1, school.name
    listed = set(offered)
    for school in schools.SCHOOLS:
        for other in (*school.local_names, *school.aliases, school.domain):
            assert other not in listed, f"{other!r} is matched, not listed"
    assert "KSU" not in listed and "جامعة الملك سعود" not in listed
    assert all(name.isascii() for name in offered)  # English names only


def test_every_school_is_still_found_by_local_name_abbreviation_domain_and_host():
    for school in schools.SCHOOLS:
        host = urlsplit(school.url).hostname
        for typed in (school.name, *school.local_names, *school.aliases, school.domain, host):
            assert schools.find(typed) is school, f"{typed!r} no longer finds {school.name}"
            assert schools.resolve(typed) == school.url, typed


def test_the_ipad_list_is_generated_from_this_one():
    spec = importlib.util.spec_from_file_location("generate_schools", ROOT / "scripts" / "generate-schools.py")
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    current = generator.SWIFT.read_text(encoding="utf-8")
    assert generator.render(current, schools) == current, "run scripts/generate-schools.py"

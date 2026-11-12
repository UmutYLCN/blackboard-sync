"""Known schools: a typed name, abbreviation or web domain becomes the Blackboard address."""

import argparse
import re
from urllib.parse import urlsplit

import pytest

from blackboard_sync import schools
from blackboard_sync.cli import make_config
from blackboard_sync.settings import SettingsError, normalize_base_url

KSU = "https://lms.ksu.edu.sa"
ISTUN = "https://blackboard.istun.edu.tr"


def _own_blackboard_host(host: str) -> bool:
    """``istinye.blackboard.com``: Blackboard hosts the site under one school-specific name."""
    label = host.removesuffix(".blackboard.com")
    return host.endswith(".blackboard.com") and "." not in label and sum(
        urlsplit(other.url).hostname == host for other in schools.SCHOOLS) == 1


def test_every_school_is_a_plain_https_address_under_its_own_domain():
    for school in schools.SCHOOLS:
        parts = urlsplit(school.url)
        assert parts.scheme == "https" and parts.path == "" and not parts.query, school.name
        assert parts.port is None and not parts.fragment and not parts.username, school.name
        assert (parts.hostname == school.domain or parts.hostname.endswith("." + school.domain)
                or _own_blackboard_host(parts.hostname)), school.name
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", school.verified), f"{school.name} needs the day it was checked"
        assert re.fullmatch(r"[A-Z]{2}", school.country), school.name


def test_only_a_blackboard_com_host_with_one_school_specific_label_may_leave_the_schools_domain():
    outside = [s for s in schools.SCHOOLS
               if not (urlsplit(s.url).hostname == s.domain or urlsplit(s.url).hostname.endswith("." + s.domain))]
    assert outside, "some schools are hosted by Blackboard under blackboard.com"
    for school in outside:
        host = urlsplit(school.url).hostname
        assert host.endswith(".blackboard.com") and host.count(".") == 2, f"{school.name}: {host}"
    assert not _own_blackboard_host("blackboard.com")
    assert not _own_blackboard_host("a.b.blackboard.com")
    assert not _own_blackboard_host("blackboard.example.com")
    assert not _own_blackboard_host("nobody.blackboard.com")  # no school has this host


def test_no_name_belongs_to_two_schools():
    owner: dict[str, str] = {}
    for school in schools.SCHOOLS:
        for key in (school.name, *school.local_names, *school.aliases, school.domain, urlsplit(school.url).hostname):
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


def test_the_list_has_the_original_sixteen_first_and_every_school_once():
    assert len(schools.SCHOOLS) >= 143
    assert [s.name for s in schools.SCHOOLS[:2]] == ["Istanbul Health and Technology University", "King Saud University"]
    assert schools.SCHOOLS[15].name == "Jazan University"
    assert all(s.verified == "2026-11-07" for s in schools.SCHOOLS[:16])
    assert all(s.verified == "2026-11-08" for s in schools.SCHOOLS[16:])
    rest = schools.SCHOOLS[16:]
    assert [(s.country, s.name.casefold()) for s in rest] == sorted((s.country, s.name.casefold()) for s in rest)
    assert len({s.url for s in schools.SCHOOLS}) == len(schools.SCHOOLS)


def test_the_five_new_turkish_schools_are_found_by_their_own_names():
    for typed, address in [
        ("Istinye University", "https://istinye.blackboard.com"),
        ("istinye.edu.tr", "https://istinye.blackboard.com"),
        ("İstinye Üniversitesi", "https://istinye.blackboard.com"),
        ("MEF Üniversitesi", "https://mef.blackboard.com"),
        ("Fenerbahçe Üniversitesi", "https://blackboard.fbu.edu.tr"),
        ("Maltepe University", "https://blackboard.maltepe.edu.tr"),
        ("Istanbul Okan University", "https://olearn.okan.edu.tr"),
    ]:
        assert schools.resolve(typed) == address, typed


def test_the_first_sixteen_schools_keep_every_match_they_had():
    for school in schools.SCHOOLS[:16]:
        for typed in (school.name, *school.local_names, *school.aliases, school.domain, urlsplit(school.url).hostname):
            assert schools.find(typed) is school, f"{typed!r} no longer finds {school.name}"


@pytest.mark.parametrize("typed", ["King", "University", "Universidad", "Üniversitesi", "جامعة", "blackboard.com", "learn.example.edu"])
def test_a_generic_word_names_no_school(typed):
    assert schools.resolve(typed) is None

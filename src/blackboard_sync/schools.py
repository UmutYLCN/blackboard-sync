"""Known schools: what the student types (a name, an abbreviation, a web domain) becomes the Blackboard address.

The settings forms accept ``King Saud University``, ``KSU`` or ``ksu.edu.sa`` as well as a full address;
``normalize_base_url`` asks ``resolve`` first. Only addresses that answered Blackboard's public
``/learn/api/public/v1/system/version`` check (``scripts/verify-schools.py``) belong in ``SCHOOLS``,
each with the date it was checked. The iPad app has the same list in
``ios/BlackboardSync/BlackboardSync/Core/Schools.swift``; ``scripts/generate-schools.py`` writes it,
and a test fails when the two differ.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class School:
    name: str  # English name, shown in lists
    url: str  # https://host, the Blackboard address
    domain: str  # the school's own web domain, which students know best
    country: str  # ISO 3166-1 alpha-2
    local_names: tuple[str, ...] = ()  # the name in the local language; matched, never shown
    aliases: tuple[str, ...] = ()  # abbreviations; matched, never shown
    verified: str = ""  # the day the address answered the Blackboard check


SCHOOLS: tuple[School, ...] = (
    School("Istanbul Health and Technology University", "https://blackboard.istun.edu.tr", "istun.edu.tr", "TR",
           ("İstanbul Sağlık ve Teknoloji Üniversitesi",), ("ISTUN",), "2026-11-07"),
    School("King Saud University", "https://lms.ksu.edu.sa", "ksu.edu.sa", "SA",
           ("جامعة الملك سعود",), ("KSU",), "2026-11-07"),
    School("Saudi Electronic University", "https://lms.seu.edu.sa", "seu.edu.sa", "SA",
           ("الجامعة السعودية الإلكترونية",), ("SEU",), "2026-11-07"),
    School("King Fahd University of Petroleum and Minerals", "https://blackboard.kfupm.edu.sa", "kfupm.edu.sa", "SA",
           ("جامعة الملك فهد للبترول والمعادن",), ("KFUPM",), "2026-11-07"),
    School("Imam Mohammad Ibn Saud Islamic University", "https://lms.imamu.edu.sa", "imamu.edu.sa", "SA",
           ("جامعة الإمام محمد بن سعود الإسلامية",), ("IMSIU", "IMAMU"), "2026-11-07"),
    School("Umm Al-Qura University", "https://lms.uqu.edu.sa", "uqu.edu.sa", "SA",
           ("جامعة أم القرى",), ("UQU",), "2026-11-07"),
    School("King Abdulaziz University", "https://lms.kau.edu.sa", "kau.edu.sa", "SA",
           ("جامعة الملك عبدالعزيز",), ("KAU",), "2026-11-07"),
    School("Qassim University", "https://lms.qu.edu.sa", "qu.edu.sa", "SA",
           ("جامعة القصيم",), (), "2026-11-07"),
    School("King Khalid University", "https://lms.kku.edu.sa", "kku.edu.sa", "SA",
           ("جامعة الملك خالد",), ("KKU",), "2026-11-07"),
    School("Taif University", "https://lms.tu.edu.sa", "tu.edu.sa", "SA",
           ("جامعة الطائف",), (), "2026-11-07"),
    School("Northern Border University", "https://lms.nbu.edu.sa", "nbu.edu.sa", "SA",
           ("جامعة الحدود الشمالية",), ("NBU",), "2026-11-07"),
    School("Prince Sattam bin Abdulaziz University", "https://lms.psau.edu.sa", "psau.edu.sa", "SA",
           ("جامعة الأمير سطام بن عبدالعزيز",), ("PSAU",), "2026-11-07"),
    School("King Faisal University", "https://lms.kfu.edu.sa", "kfu.edu.sa", "SA",
           ("جامعة الملك فيصل",), ("KFU",), "2026-11-07"),
    School("Taibah University", "https://lms.taibahu.edu.sa", "taibahu.edu.sa", "SA",
           ("جامعة طيبة",), (), "2026-11-07"),
    School("University of Jeddah", "https://lms.ju.edu.sa", "ju.edu.sa", "SA",
           ("جامعة جدة",), (), "2026-11-07"),
    School("Jazan University", "https://lms.jazanu.edu.sa", "jazanu.edu.sa", "SA",
           ("جامعة جازان",), (), "2026-11-07"),
)

# Letters that look different but are typed interchangeably (Arabic ة/ه and ى/ي, Turkish dotless ı).
_SAME_LETTER = str.maketrans({"ı": "i", "ة": "ه", "ى": "ي", "ـ": ""})


def fold(text: str) -> str:
    """Lower case, no accents or marks, one space between words: ``İstanbul`` and ``istanbul`` match.

    Arabic hamza forms of alef (أ إ آ) fold to a plain alef and the vowel marks go. The Swift
    twin in ``Schools.swift`` follows the same steps.
    """
    decomposed = unicodedata.normalize("NFKD", text or "")
    bare = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    return re.sub(r"[\W_]+", " ", bare.lower().translate(_SAME_LETTER)).strip()


def _host(url: str) -> str:
    return urlsplit(url).hostname or ""


def _index() -> dict[str, School]:
    index: dict[str, School] = {}
    for school in SCHOOLS:
        for key in (school.name, *school.local_names, *school.aliases, school.domain, _host(school.url)):
            index.setdefault(fold(key), school)
    return index


_INDEX = _index()


def find(text: str) -> School | None:
    """The school the student means by ``text``: its name, abbreviation, web domain or Blackboard host.

    Text with a scheme is already an address, so it names no school.
    """
    text = (text or "").strip()
    return None if not text or "://" in text else _INDEX.get(fold(text))


def resolve(text: str) -> str | None:
    """The Blackboard address of the school ``text`` names, or None when it names no known school."""
    school = find(text)
    return school.url if school else None


def suggestions() -> list[str]:
    """What a search list offers: each school once, by its English name, in ``SCHOOLS`` order.

    Local-language names are not listed, but ``find`` and ``resolve`` still match them.
    """
    return [school.name for school in SCHOOLS]

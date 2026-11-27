"""Built-in offline Demo Mode for App Review and trying Blackboard Sync without a university account.

When the school address is ``DEMO_BASE_URL`` (``https://demo.blackboard.invalid``), sign-in and
sync run completely in-process against ``DemoTransport`` without making any network requests.
The real ``Syncer`` writes real course folders, sample PDF handouts, rendered announcement PDFs,
and relative grade-column deadlines into the folder the user chose, so Home, Sync activity,
Courses, Announcements, Calendar, and Finder all work identically to a live university account.
"""

from __future__ import annotations

import copy
import functools
import json
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Mapping
from urllib.parse import parse_qs, urlsplit

import requests

from blackboard_sync import notepdf
from blackboard_sync.api import BlackboardClient
from blackboard_sync.session import save_session

if TYPE_CHECKING:
    from blackboard_sync.config import Config

DEMO_BASE_URL = "https://demo.blackboard.invalid"
DEMO_SCHOOL_LABEL = "Demo University"
DEMO_USER = {
    "id": "_demo_user_1",
    "userName": "alex.morgan",
    "displayName": "Alex Morgan (Demo)",
    "name": {"given": "Alex", "family": "Morgan"},
}


def is_demo_url(url: str | None) -> bool:
    """True when ``url`` selects the built-in offline Demo Mode."""
    cleaned = (url or "").strip().rstrip("/").lower()
    return cleaned in (DEMO_BASE_URL, "demo.blackboard.invalid", "demo")


def save_demo_session(config: Config) -> dict:
    """Write a local demo session into ``config.session_file``; never touches the network."""
    config.ensure_data_dir()
    cookies = [
        {
            "name": "BbRouter",
            "value": "demo-session-token",
            "domain": "demo.blackboard.invalid",
            "path": "/",
            "secure": True,
            "expires": None,
        }
    ]
    save_session(config.session_file, DEMO_BASE_URL, cookies, DEMO_USER)
    return dict(DEMO_USER)


@functools.lru_cache(maxsize=16)
def _demo_pdf(markdown: str) -> bytes:
    return notepdf.render_pdf(markdown)


class _DemoResponse:
    def __init__(
        self,
        status_code: int = 200,
        url: str = "",
        json_body: dict | None = None,
        content: bytes = b"",
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.url = url
        self._json = json_body
        self.content = content if json_body is None else json.dumps(json_body).encode("utf-8")
        self.headers = dict(headers) if headers is not None else (
            {"Content-Type": "application/json"} if json_body is not None else {}
        )

    def json(self) -> dict:
        if self._json is None:
            raise ValueError("Response body is not JSON")
        return self._json

    def iter_content(self, chunk_size: int = 65536):
        for offset in range(0, len(self.content), chunk_size):
            yield self.content[offset : offset + chunk_size]

    def close(self) -> None:
        pass


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _term_label(now: datetime) -> str:
    year = now.year
    if now.month >= 8:
        return f"{year}-{year + 1} Fall"
    return f"{year - 1}-{year} Spring"


def _build_fixture_data(now: datetime) -> tuple[dict[str, dict], dict[str, tuple[bytes, str]]]:
    term_id = "_demo_term_1"
    term_name = _term_label(now)
    term_start = _iso(now - timedelta(days=45))
    term_end = _iso(now + timedelta(days=90))
    course_created = _iso(now - timedelta(days=40))

    # Fixed recent timestamps within the day so repeated syncs see unchanged items (fast 0-change re-syncs),
    # while relative deadlines always keep Upcoming and Past due populated whenever App Review runs.
    anchor = now.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    mod_base = _iso(anchor - timedelta(days=7))
    ann_1 = _iso(anchor - timedelta(hours=5))
    ann_2 = _iso(anchor - timedelta(days=1, hours=2))
    ann_3 = _iso(anchor - timedelta(days=2, hours=4))
    ann_4 = _iso(anchor - timedelta(days=3))

    due_today = _iso(anchor + timedelta(hours=6))
    due_soon = _iso(anchor + timedelta(days=2, hours=9))
    due_week = _iso(anchor + timedelta(days=5, hours=11))
    due_later = _iso(anchor + timedelta(days=9, hours=8))
    due_past = _iso(anchor - timedelta(days=2, hours=3))

    cs_id = "_demo_cs204_1"
    math_id = "_demo_math210_1"
    phys_id = "_demo_phys102_1"
    hist_id = "_demo_hist115_1"

    routes: dict[str, dict] = {
        "/learn/api/public/v1/users/me": dict(DEMO_USER),
        f"/learn/api/public/v1/terms/{term_id}": {
            "id": term_id,
            "name": term_name,
            "availability": {
                "available": "Yes",
                "duration": {"type": "DateRange", "start": term_start, "end": term_end},
            },
        },
        f"/learn/api/public/v1/users/{DEMO_USER['id']}/courses": {
            "results": [
                {
                    "id": "_dm_1",
                    "userId": DEMO_USER["id"],
                    "courseId": cs_id,
                    "courseRoleId": "Student",
                    "availability": {"available": "Yes"},
                    "course": {
                        "id": cs_id,
                        "courseId": "CS204",
                        "name": "Data Structures and Algorithms",
                        "termId": term_id,
                        "created": course_created,
                        "ultraStatus": "Ultra",
                        "availability": {"available": "Yes"},
                    },
                },
                {
                    "id": "_dm_2",
                    "userId": DEMO_USER["id"],
                    "courseId": math_id,
                    "courseRoleId": "Student",
                    "availability": {"available": "Yes"},
                    "course": {
                        "id": math_id,
                        "courseId": "MATH210",
                        "name": "Linear Algebra",
                        "termId": term_id,
                        "created": course_created,
                        "ultraStatus": "Ultra",
                        "availability": {"available": "Yes"},
                    },
                },
                {
                    "id": "_dm_3",
                    "userId": DEMO_USER["id"],
                    "courseId": phys_id,
                    "courseRoleId": "Student",
                    "availability": {"available": "Yes"},
                    "course": {
                        "id": phys_id,
                        "courseId": "PHYS102",
                        "name": "Electricity and Magnetism",
                        "termId": term_id,
                        "created": course_created,
                        "ultraStatus": "Ultra",
                        "availability": {"available": "Yes"},
                    },
                },
                {
                    "id": "_dm_4",
                    "userId": DEMO_USER["id"],
                    "courseId": hist_id,
                    "courseRoleId": "Student",
                    "availability": {"available": "Yes"},
                    "course": {
                        "id": hist_id,
                        "courseId": "HIST115",
                        "name": "Modern World History",
                        "termId": term_id,
                        "created": course_created,
                        "ultraStatus": "Ultra",
                        "availability": {"available": "Yes"},
                    },
                },
            ]
        },
        # CS204 contents
        f"/learn/api/public/v1/courses/{cs_id}/contents": {
            "results": [
                {
                    "id": "_cs_syl",
                    "title": "Course Syllabus.pdf",
                    "position": 0,
                    "modified": mod_base,
                    "contentHandler": {"id": "resource/x-bb-file", "file": {"fileName": "CS204_Course_Syllabus.pdf"}},
                },
                {
                    "id": "_cs_wk1",
                    "title": "Lecture Slides",
                    "position": 1,
                    "hasChildren": True,
                    "modified": mod_base,
                    "contentHandler": {"id": "resource/x-bb-folder"},
                },
                {
                    "id": "_cs_ps2",
                    "title": "Problem Set 2: Balanced Search Trees",
                    "position": 2,
                    "modified": ann_2,
                    "contentHandler": {"id": "resource/x-bb-asmt-test-link"},
                    "description": (
                        "<p>Implement AVL rotations and prove the O(log n) height bound.</p>"
                        "<p>Submit your written analysis and test cases as a single PDF.</p>"
                    ),
                },
                {
                    "id": "_cs_ps1",
                    "title": "Problem Set 1: Recurrence Relations",
                    "position": 3,
                    "modified": mod_base,
                    "contentHandler": {"id": "resource/x-bb-asmt-test-link"},
                    "description": "<p>Master theorem and recursion-tree practice problems.</p>",
                },
            ]
        },
        f"/learn/api/public/v1/courses/{cs_id}/contents/_cs_syl/attachments": {
            "results": [{"id": "_att_cs_syl", "fileName": "CS204_Course_Syllabus.pdf", "mimeType": "application/pdf"}]
        },
        f"/learn/api/public/v1/courses/{cs_id}/contents/_cs_wk1/children": {
            "results": [
                {
                    "id": "_cs_wk1_f",
                    "title": "Week 1 - Asymptotic Complexity.pdf",
                    "position": 0,
                    "modified": mod_base,
                    "contentHandler": {
                        "id": "resource/x-bb-file",
                        "file": {"fileName": "Week_1_Asymptotic_Complexity.pdf"},
                    },
                }
            ]
        },
        f"/learn/api/public/v1/courses/{cs_id}/contents/_cs_wk1_f/attachments": {
            "results": [
                {"id": "_att_cs_wk1", "fileName": "Week_1_Asymptotic_Complexity.pdf", "mimeType": "application/pdf"}
            ]
        },
        f"/learn/api/public/v1/courses/{cs_id}/contents/_cs_ps2/attachments": {"results": []},
        f"/learn/api/public/v1/courses/{cs_id}/contents/_cs_ps1/attachments": {"results": []},
        f"/learn/api/public/v1/courses/{cs_id}/announcements": {
            "results": [
                {
                    "id": "_ann_cs_1",
                    "title": "Midterm Review Session & Practice Packet",
                    "draft": False,
                    "body": (
                        "<p>We will hold an optional review session on Thursday at 17:00 in Hall B201 "
                        "covering asymptotic bounds, heaps, and balanced trees.</p>"
                    ),
                    "created": ann_1,
                    "modified": ann_1,
                    "availability": {"duration": {"type": "Permanent"}},
                },
                {
                    "id": "_ann_cs_2",
                    "title": "Office Hours Updated for Problem Set 2",
                    "draft": False,
                    "body": "<p>TA office hours move to Engineering 304 this week.</p>",
                    "created": ann_4,
                    "modified": ann_4,
                    "availability": {"duration": {"type": "Permanent"}},
                },
            ]
        },
        f"/learn/api/public/v2/courses/{cs_id}/gradebook/columns": {
            "results": [
                {
                    "id": "_gc_cs_ps2",
                    "name": "Problem Set 2: Balanced Search Trees",
                    "contentId": "_cs_ps2",
                    "availability": {"available": "Yes"},
                    "grading": {"due": due_today},
                },
                {
                    "id": "_gc_cs_ps1",
                    "name": "Problem Set 1: Recurrence Relations",
                    "contentId": "_cs_ps1",
                    "availability": {"available": "Yes"},
                    "grading": {"due": due_past},
                },
            ]
        },
        # MATH210 contents
        f"/learn/api/public/v1/courses/{math_id}/contents": {
            "results": [
                {
                    "id": "_math_eig",
                    "title": "Eigenvalues & Diagonalization Notes.pdf",
                    "position": 0,
                    "modified": ann_2,
                    "contentHandler": {
                        "id": "resource/x-bb-file",
                        "file": {"fileName": "MATH210_Eigenvalues_Notes.pdf"},
                    },
                },
                {
                    "id": "_math_hw4",
                    "title": "Homework 4: Orthogonality & Least Squares",
                    "position": 1,
                    "modified": ann_2,
                    "contentHandler": {"id": "resource/x-bb-asmt-test-link"},
                    "description": "<p>Complete exercises 6.2 #1-8 and 6.5 #3-6 showing full Gram-Schmidt steps.</p>",
                },
            ]
        },
        f"/learn/api/public/v1/courses/{math_id}/contents/_math_eig/attachments": {
            "results": [
                {"id": "_att_math_eig", "fileName": "MATH210_Eigenvalues_Notes.pdf", "mimeType": "application/pdf"}
            ]
        },
        f"/learn/api/public/v1/courses/{math_id}/contents/_math_hw4/attachments": {"results": []},
        f"/learn/api/public/v1/courses/{math_id}/announcements": {
            "results": [
                {
                    "id": "_ann_math_1",
                    "title": "Eigenvalues Handout Posted",
                    "draft": False,
                    "body": "<p>Worked examples on characteristic polynomials and diagonalization are now available.</p>",
                    "created": ann_2,
                    "modified": ann_2,
                    "availability": {"duration": {"type": "Permanent"}},
                }
            ]
        },
        f"/learn/api/public/v2/courses/{math_id}/gradebook/columns": {
            "results": [
                {
                    "id": "_gc_math_hw4",
                    "name": "Homework 4: Orthogonality & Least Squares",
                    "contentId": "_math_hw4",
                    "availability": {"available": "Yes"},
                    "grading": {"due": due_soon},
                }
            ]
        },
        # PHYS102 contents
        f"/learn/api/public/v1/courses/{phys_id}/contents": {
            "results": [
                {
                    "id": "_phys_lab2",
                    "title": "Lab 2 - RC Circuits Manual.pdf",
                    "position": 0,
                    "modified": ann_3,
                    "contentHandler": {
                        "id": "resource/x-bb-file",
                        "file": {"fileName": "PHYS102_Lab_2_RC_Circuits.pdf"},
                    },
                },
                {
                    "id": "_phys_rep2",
                    "title": "Lab Report 2: Time Constant Measurement",
                    "position": 1,
                    "modified": ann_3,
                    "contentHandler": {"id": "resource/x-bb-asmt-test-link"},
                    "description": "<p>Include oscilloscope plots, uncertainty propagation, and discussion.</p>",
                },
            ]
        },
        f"/learn/api/public/v1/courses/{phys_id}/contents/_phys_lab2/attachments": {
            "results": [
                {"id": "_att_phys_lab2", "fileName": "PHYS102_Lab_2_RC_Circuits.pdf", "mimeType": "application/pdf"}
            ]
        },
        f"/learn/api/public/v1/courses/{phys_id}/contents/_phys_rep2/attachments": {"results": []},
        f"/learn/api/public/v1/courses/{phys_id}/announcements": {
            "results": [
                {
                    "id": "_ann_phys_1",
                    "title": "Lab Safety & Oscilloscope Bench Assignments",
                    "draft": False,
                    "body": "<p>Please review the RC circuit pre-lab questions before arriving at Lab 108.</p>",
                    "created": ann_3,
                    "modified": ann_3,
                    "availability": {"duration": {"type": "Permanent"}},
                }
            ]
        },
        f"/learn/api/public/v2/courses/{phys_id}/gradebook/columns": {
            "results": [
                {
                    "id": "_gc_phys_rep2",
                    "name": "Lab Report 2: Time Constant Measurement",
                    "contentId": "_phys_rep2",
                    "availability": {"available": "Yes"},
                    "grading": {"due": due_week},
                }
            ]
        },
        # HIST115 contents
        f"/learn/api/public/v1/courses/{hist_id}/contents": {
            "results": [
                {
                    "id": "_hist_reader",
                    "title": "Primary Sources Reader - Unit 3.pdf",
                    "position": 0,
                    "modified": mod_base,
                    "contentHandler": {
                        "id": "resource/x-bb-file",
                        "file": {"fileName": "HIST115_Primary_Sources_Unit_3.pdf"},
                    },
                },
                {
                    "id": "_hist_essay",
                    "title": "Source Analysis Essay 1",
                    "position": 1,
                    "modified": mod_base,
                    "contentHandler": {"id": "resource/x-bb-asmt-test-link"},
                    "description": "<p>Write a 1,200-word comparative analysis of two primary sources from Unit 3.</p>",
                },
            ]
        },
        f"/learn/api/public/v1/courses/{hist_id}/contents/_hist_reader/attachments": {
            "results": [
                {
                    "id": "_att_hist_reader",
                    "fileName": "HIST115_Primary_Sources_Unit_3.pdf",
                    "mimeType": "application/pdf",
                }
            ]
        },
        f"/learn/api/public/v1/courses/{hist_id}/contents/_hist_essay/attachments": {"results": []},
        f"/learn/api/public/v1/courses/{hist_id}/announcements": {"results": []},
        f"/learn/api/public/v2/courses/{hist_id}/gradebook/columns": {
            "results": [
                {
                    "id": "_gc_hist_essay",
                    "name": "Source Analysis Essay 1",
                    "contentId": "_hist_essay",
                    "availability": {"available": "Yes"},
                    "grading": {"due": due_later},
                }
            ]
        },
    }

    files: dict[str, tuple[bytes, str]] = {
        f"/learn/api/public/v1/courses/{cs_id}/contents/_cs_syl/attachments/_att_cs_syl/download": (
            _demo_pdf(
                "# CS204 Data Structures and Algorithms\n\n"
                "**Demo Course Syllabus** — Sample document generated locally by Blackboard Sync Demo Mode.\n\n"
                "## Topics\n"
                "- Asymptotic complexity and recurrence relations\n"
                "- Priority queues, heaps, and balanced binary search trees\n"
                "- Graph traversal, shortest paths, and minimum spanning trees\n"
            ),
            '"demo-cs204-syl-v1"',
        ),
        f"/learn/api/public/v1/courses/{cs_id}/contents/_cs_wk1_f/attachments/_att_cs_wk1/download": (
            _demo_pdf(
                "# Week 1 — Asymptotic Complexity\n\n"
                "Big-O, Big-Omega, and Big-Theta bounds describe growth rates independent of hardware constants.\n\n"
                "## Key Definitions\n"
                "1. **Upper bound:** `f(n) = O(g(n))` when `f(n) <= c * g(n)` for all `n >= n0`.\n"
                "2. **Tight bound:** `f(n) = Theta(g(n))` when bounded both above and below.\n"
            ),
            '"demo-cs204-wk1-v1"',
        ),
        f"/learn/api/public/v1/courses/{math_id}/contents/_math_eig/attachments/_att_math_eig/download": (
            _demo_pdf(
                "# MATH210 — Eigenvalues & Diagonalization\n\n"
                "A nonzero vector `v` is an eigenvector of square matrix `A` with eigenvalue `lambda` if `Av = lambda v`.\n\n"
                "- Solve `det(A - lambda I) = 0` for the characteristic polynomial.\n"
                "- Diagonalize `A = P D P^-1` when `n` linearly independent eigenvectors exist.\n"
            ),
            '"demo-math210-eig-v1"',
        ),
        f"/learn/api/public/v1/courses/{phys_id}/contents/_phys_lab2/attachments/_att_phys_lab2/download": (
            _demo_pdf(
                "# PHYS102 — Lab 2: RC Circuits\n\n"
                "Measure the charging and discharging curve `V(t) = V0 * exp(-t / RC)` across a precision capacitor.\n\n"
                "- Record voltage at 5 time constants.\n"
                "- Fit `ln(V / V0)` vs. `t` to extract `tau = R * C`.\n"
            ),
            '"demo-phys102-lab2-v1"',
        ),
        f"/learn/api/public/v1/courses/{hist_id}/contents/_hist_reader/attachments/_att_hist_reader/download": (
            _demo_pdf(
                "# HIST115 — Primary Sources Reader (Unit 3)\n\n"
                "Selected excerpts and guiding questions for seminar discussion and Source Analysis Essay 1.\n"
            ),
            '"demo-hist115-reader-v1"',
        ),
    }
    return routes, files


class DemoTransport:
    """In-memory ``requests.Session`` stand-in serving ``DEMO_BASE_URL`` with zero network I/O."""

    def __init__(self, now: datetime | None = None) -> None:
        current = now or datetime.now(timezone.utc)
        self._routes, self._files = _build_fixture_data(current)
        self.headers: dict[str, str] = {}
        self.cookies = requests.cookies.RequestsCookieJar()

    def get(self, url: str, params=None, timeout=None, stream: bool = False, headers=None) -> _DemoResponse:
        parts = urlsplit(url)
        query = parse_qs(parts.query)
        if params:
            query.update({k: [str(v)] for k, v in params.items()})
        key = parts.path
        if "offset" in query:
            key += f"?offset={query['offset'][0]}"
        if key in self._files:
            payload, etag = self._files[key]
            resp_headers = {
                "Content-Type": "application/pdf",
                "Content-Length": str(len(payload)),
                "ETag": etag,
            }
            if (headers or {}).get("If-None-Match") == etag:
                return _DemoResponse(304, url, content=b"", headers=resp_headers)
            return _DemoResponse(200, url, content=payload, headers=resp_headers)
        if key in self._routes:
            return _DemoResponse(200, url, json_body=copy.deepcopy(self._routes[key]))
        return _DemoResponse(404, url, json_body={"status": 404, "message": "Not found"})

    def close(self) -> None:
        pass


def open_demo_client(now: datetime | None = None) -> tuple[BlackboardClient, dict]:
    """Open an offline ``BlackboardClient`` and session dict for ``DEMO_BASE_URL``."""
    session_data = {
        "base_url": DEMO_BASE_URL,
        "saved_at": (now or datetime.now(timezone.utc)).timestamp(),
        "user": dict(DEMO_USER),
        "cookies": [],
    }
    return BlackboardClient(DEMO_BASE_URL, DemoTransport(now=now)), session_data

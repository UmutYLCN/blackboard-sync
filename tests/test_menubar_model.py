from datetime import datetime, timedelta, timezone
from pathlib import Path

from blackboard_sync.settings import Settings
from blackboard_sync.menubar.model import (
    FIRST_SYNC_DELAY,
    RETRY_DELAY,
    SYNC_INTERVAL,
    AppModel,
    Icon,
    RecentItem,
    RunOutcome,
    changes_notification,
    course_line,
    format_time,
    load_saved_state,
    open_target,
    parse_sync_output,
    sync_arguments,
    unique_labels,
)
from blackboard_sync.menubar.settings_form import window_status

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)
DEST = Path("/Users/student/Documents/University")
CSE = "2026-2027 Güz/CSE303 Algorithm Analysis"
MTH = "2026-2027 Güz/MTH201 Linear Algebra"


def report(status="ok", courses=None, finished_at="2026-10-03T12:00:09+00:00", message=""):
    return {
        "status": status,
        "message": message,
        "finished_at": finished_at,
        "dest": str(DEST),
        "courses": courses or [],
    }


def course(code, folder, **changes):
    data = {"code": code, "name": code, "folder": folder}
    data.update(changes)
    return data


CHANGED = report(
    courses=[
        course(
            "CSE303",
            CSE,
            new_files=[f"{CSE}/Lecture Notes/Week 2/week2.pdf", f"{CSE}/hw2.pdf"],
            new_announcements=[f"{CSE}/Duyurular/2026-10-03 Quiz.md"],
        ),
        course("MTH201", MTH),
    ]
)


def outcome(data=CHANGED):
    return RunOutcome.from_report(data)


def model(**kwargs):
    return AppModel(dest=DEST, now=NOW, **kwargs)


# -- parsing the CLI output --------------------------------------------------

def test_json_summary_is_parsed():
    result = parse_sync_output(
        '{"status": "ok", "finished_at": "2026-10-03T12:00:09+00:00", "courses": []}', 0, "", NOW
    )
    assert result.status == "ok"
    assert result.finished_at == datetime(2026, 10, 3, 12, 0, 9, tzinfo=timezone.utc)


def test_exit_code_is_the_fallback_without_json():
    assert parse_sync_output("", 3, "", NOW).status == "login_required"
    assert parse_sync_output("", 4, "", NOW).status == "locked"
    crashed = parse_sync_output("", 1, "Traceback ...\nValueError: boom\n", NOW)
    assert crashed.status == "error"
    assert crashed.message == "ValueError: boom"
    assert crashed.finished_at == NOW


# -- notification text -------------------------------------------------------

def test_course_line_is_turkish_and_singular():
    cse = outcome().courses[0]
    assert course_line(cse) == "CSE303: 2 yeni dosya, 1 yeni duyuru"


def test_notification_lists_each_changed_course_and_opens_its_folder():
    note = changes_notification(outcome(), DEST)
    assert note.message == "CSE303: 2 yeni dosya, 1 yeni duyuru"
    assert note.data == {"open": str(DEST / CSE)}


def test_notification_for_several_courses_opens_their_common_folder():
    data = report(
        courses=[
            course("CSE303", CSE, new_files=[f"{CSE}/a.pdf"]),
            course("MTH201", MTH, updated_files=[f"{MTH}/b.pdf"], new_notes=[f"{MTH}/c.md"]),
        ]
    )
    note = changes_notification(outcome(data), DEST)
    assert note.message.splitlines() == [
        "CSE303: 1 yeni dosya",
        "MTH201: 1 güncellenen dosya, 1 yeni not",
    ]
    assert note.data == {"open": str(DEST / "2026-2027 Güz")}


def test_no_notification_when_nothing_is_new():
    assert changes_notification(outcome(report(courses=[course("MTH201", MTH)])), DEST) is None


# -- scheduling --------------------------------------------------------------

def test_first_sync_runs_shortly_after_start_then_hourly():
    m = model()
    assert not m.due(NOW)
    assert m.due(NOW + FIRST_SYNC_DELAY)
    assert m.begin("sync")
    later = NOW + FIRST_SYNC_DELAY
    m.finish_sync(outcome(), later)
    assert not m.due(later + SYNC_INTERVAL - timedelta(seconds=1))
    assert m.due(later + SYNC_INTERVAL)


def test_never_overlaps_a_running_job():
    m = model()
    assert m.begin("sync")
    assert not m.due(NOW + timedelta(days=1))
    assert not m.begin("sync")
    assert not m.begin("login")


def test_locked_run_keeps_the_last_result_and_retries_soon():
    m = model(last=outcome())
    m.begin("sync")
    notes = m.finish_sync(RunOutcome(status="locked"), NOW)
    assert notes == []
    assert m.last.status == "ok"
    assert m.next_run_at == NOW + RETRY_DELAY
    assert "Başka bir senkron" in " ".join(m.status_lines(NOW))


def test_error_retries_soon_and_shows_error_icon():
    m = model()
    m.begin("sync")
    notes = m.finish_sync(RunOutcome(status="error", message="Network error", finished_at=NOW), NOW)
    assert notes == []
    assert m.icon() == Icon.ERROR
    assert m.next_run_at == NOW + RETRY_DELAY
    assert m.status_lines(NOW) == [
        f"{format_time(NOW, NOW)} denendi · hata · Network error · sonraki: {format_time(NOW + RETRY_DELAY, NOW)}"
    ]


# -- session expiry ----------------------------------------------------------

def test_expired_session_notifies_once_until_it_works_again():
    m = model()
    expired = RunOutcome(status="login_required", finished_at=NOW)
    for hour in range(3):
        m.begin("sync")
        notes = m.finish_sync(expired, NOW + timedelta(hours=hour))
        assert [n.data for n in notes] == ([{"action": "login"}] if hour == 0 else [])
        assert m.icon() == Icon.EXPIRED

    m.begin("sync")
    m.finish_sync(outcome(), NOW + timedelta(hours=3))
    assert m.icon() == Icon.IDLE
    m.begin("sync")
    assert len(m.finish_sync(expired, NOW + timedelta(hours=4))) == 1


def test_successful_login_makes_a_sync_due_now():
    m = model(last=RunOutcome(status="login_required", finished_at=NOW))
    assert m.begin("login")
    login = m.menu(NOW).entries[0]
    assert (login.title, login.action, login.enabled) == ("Giriş bekleniyor…", "login", False)
    m.finish_login(True, "", NOW + timedelta(minutes=2))
    assert m.due(NOW + timedelta(minutes=2))


def test_waiting_for_sign_in_names_the_browser_or_the_app_window():
    m = model()
    m.begin("login")
    assert m.status_lines(NOW)[0] == "Tarayıcıda giriş yapmanız bekleniyor…"  # not known
    m.login_method = "Opera GX"
    assert m.status_lines(NOW)[0] == "Opera GX penceresinde giriş yapmanız bekleniyor…"
    m.login_method = "inapp"
    assert m.status_lines(NOW)[0] == "Açılan pencerede giriş yapmanız bekleniyor…"
    m.finish_login(True, "", NOW)
    assert m.login_method == ""


def test_failed_login_is_shown():
    m = model()
    m.begin("login")
    m.finish_login(False, "The browser did not start.", NOW)
    assert m.busy is None
    assert "Giriş tamamlanamadı: The browser did not start." in m.status_lines(NOW)


# -- icon and menu -----------------------------------------------------------

def test_icon_states():
    m = model()
    assert m.icon() == Icon.IDLE
    m.begin("sync")
    assert m.icon() == Icon.SYNCING


def test_menu_after_a_sync_with_new_files():
    m = model()
    m.begin("sync")
    m.finish_sync(outcome(), NOW)
    menu = m.menu(NOW)
    assert menu.status_lines == [
        f"{format_time(NOW, NOW)} senkronize edildi · 2 yeni dosya, 1 yeni duyuru · sonraki: {format_time(NOW + SYNC_INTERVAL, NOW)}",
    ]
    m.session = signed_session()
    assert m.menu(NOW).status_lines == [
        f"✓ Ada Student · {format_time(NOW, NOW)} senkronize edildi",
        f"2 yeni dosya, 1 yeni duyuru · sonraki: {format_time(NOW + SYNC_INTERVAL, NOW)}",
    ]
    assert menu.sync_enabled and menu.entries[0].action == "login" and menu.entries[0].enabled
    assert [label for label, _ in menu.recent] == [
        f"{NOW.astimezone():%d.%m %H:%M} · CSE303 · week2.pdf",
        f"{NOW.astimezone():%d.%m %H:%M} · CSE303 · hw2.pdf",
        f"{NOW.astimezone():%d.%m %H:%M} · CSE303 · 2026-10-03 Quiz.md",
    ]


def test_menu_while_syncing_and_before_any_sync():
    m = model()
    assert m.menu(NOW).status_lines[0].startswith("Henüz senkronize edilmedi · sonraki: ")
    m.begin("sync")
    menu = m.menu(NOW)
    assert menu.sync_enabled is False
    assert menu.sync_title == "Senkronize ediliyor…"
    assert menu.status_lines == ["Yeni içerik kontrol ediliyor…"]
    # Every status line differs from the item titles (menu items are keyed by text).
    assert not set(menu.status_lines) & {e.title for e in menu.entries if e.enabled}


def test_nothing_new_line():
    m = model()
    m.begin("sync")
    m.finish_sync(outcome(report(courses=[course("MTH201", MTH)])), NOW)
    assert "· yeni bir şey yok · sonraki: " in m.status_lines(NOW)[0]


def test_recent_items_are_newest_first_deduplicated_and_capped():
    m = model()
    for i in range(12):
        m.begin("sync")
        m.finish_sync(outcome(report(courses=[course("CSE303", CSE, new_files=[f"{CSE}/f{i}.pdf"])])), NOW)
    m.begin("sync")
    m.finish_sync(outcome(report(courses=[course("CSE303", CSE, updated_files=[f"{CSE}/f5.pdf"])])), NOW)
    paths = [item.path for item in m.recent]
    assert len(paths) == 10
    assert paths[:3] == [f"{CSE}/f5.pdf", f"{CSE}/f11.pdf", f"{CSE}/f10.pdf"]
    assert len(set(paths)) == len(paths)


def test_equal_labels_are_made_unique():
    assert unique_labels([("a", "1"), ("a", "2"), ("b", "3")]) == [
        ("a", "1"),
        ("a (2)", "2"),
        ("b", "3"),
    ]


def test_format_time():
    local_noon = datetime(2026, 10, 3, 12, 0).astimezone()
    assert format_time(local_noon, local_noon + timedelta(hours=2)) == "12:00"
    assert format_time(local_noon, local_noon + timedelta(days=1)) == "dün 12:00"
    assert format_time(local_noon, local_noon + timedelta(days=5)) == "03.10 12:00"


# -- opening recent items ----------------------------------------------------

def test_open_target_prefers_the_file_then_the_nearest_folder():
    rel = f"{CSE}/Week 2/week2.pdf"
    present = {DEST / rel, DEST / CSE, DEST}
    assert open_target(DEST, rel, exists=lambda p: p in present) == DEST / rel
    present.discard(DEST / rel)
    assert open_target(DEST, rel, exists=lambda p: p in present) == DEST / CSE
    assert open_target(DEST, rel, exists=lambda p: False) is None


# -- saved state -------------------------------------------------------------

def test_saved_state_round_trip():
    m = model(recent=[RecentItem(path="a.pdf", course="CSE303", at="2026-10-03T12:00:00+00:00")])
    m.login_prompted = True
    recent, prompted = load_saved_state(m.saved_state())
    assert recent == m.recent and prompted is True
    assert load_saved_state({"recent": [{"bad": 1}]}) == ([], False)
    assert load_saved_state(None) == ([], False)


# -- "Silinenleri tekrar indir" ---------------------------------------------

def test_only_the_refetch_job_brings_back_deleted_files():
    settings = Settings(base_url="https://bb.example.edu", dest=DEST)
    common = ["--base-url", "https://bb.example.edu", "sync", "--json", "--dest", str(DEST)]
    assert sync_arguments("sync", settings) == common
    assert sync_arguments("refetch", settings) == common + ["--refetch-missing"]


def test_scheduled_runs_stay_plain_syncs_after_a_refetch():
    # The scheduler and "Şimdi senkronize et" always claim the "sync" job.
    m = model()
    assert m.begin("refetch")
    m.finish_sync(outcome(), NOW)
    assert m.busy is None
    assert m.due(NOW + SYNC_INTERVAL)


def test_refetch_shares_the_single_job_slot():
    m = model()
    assert m.begin("refetch")
    assert m.icon() == Icon.SYNCING
    assert not m.begin("sync") and not m.begin("login") and not m.begin("refetch")
    assert not m.due(NOW + timedelta(days=1))
    menu = m.menu(NOW)
    assert (menu.sync_enabled, menu.entries[0].enabled) == (False, False)
    assert menu.status_lines == ["Silinen dosyalar tekrar indiriliyor…"]
    status = window_status(m)
    assert (status.refetch_title, status.refetch_enabled, status.account_enabled) == ("Silinenler indiriliyor…", False, False)


def test_locked_refetch_asks_the_student_to_try_again():
    m = model(last=outcome())
    m.begin("refetch")
    assert m.finish_sync(RunOutcome(status="locked"), NOW) == []
    assert m.note == "Başka bir senkron sürüyor; birazdan tekrar deneyin."
    assert m.next_run_at == NOW + RETRY_DELAY  # the retry is a normal sync


def test_refetch_notification_is_one_line_per_course():
    many = [f"{CSE}/Week {i}/slides{i}.pdf" for i in range(40)]
    data = report(
        courses=[
            course("CSE303", CSE, new_files=many, new_notes=[f"{CSE}/Homework 1.md"]),
            course("MTH201", MTH, new_files=[f"{MTH}/a.pdf", f"{MTH}/b.pdf"]),
        ]
    )
    m = model()
    m.begin("refetch")
    notes = m.finish_sync(outcome(data), NOW)
    assert len(notes) == 1
    assert notes[0].message.splitlines() == [
        "CSE303: 40 yeni dosya, 1 yeni not",
        "MTH201: 2 yeni dosya",
    ]
    status = window_status(m)
    assert status.refetch_enabled and status.refetch_title == "Silinenleri tekrar indir"


def entries(menu):
    for entry in menu.entries:
        yield entry
        yield from entry.children


def signed_session(at=NOW):
    return {"saved_at": at.timestamp(), "user": {"id": "student", "displayName": "Ada Student"}}


def test_signed_in_menu_structure():
    m = model(session=signed_session(), last=outcome(), autostart=True)
    menu = m.menu(NOW)
    assert [e.title for e in menu.entries] == [
        f"✓ Ada Student · {format_time(NOW, NOW)} senkronize edildi",
        f"2 yeni dosya, 1 yeni duyuru · sonraki: {format_time(m.next_run_at, NOW)}",
        "",
        "Şimdi senkronize et", "Dersler", "Son indirilenler", "University klasörünü aç",
        "",
        "Ayarlar…", "Çık",
    ]
    assert not any(e.action in ("login", "logout", "refetch", "autostart", "check_updates") for e in entries(menu))
    assert not menu.entries[0].enabled and not menu.entries[1].enabled


def test_folder_item_is_named_after_the_destination():
    assert model().menu(NOW).entries[-4].title == "University klasörünü aç"
    m = AppModel(dest=Path("/Users/student/Documents/Okul"), now=NOW)  # an existing user's folder
    folder = next(e for e in m.menu(NOW).entries if e.action == "folder")
    assert folder.title == "Okul klasörünü aç"
    m.apply_settings(Path("/Volumes/USB/Ders Notları"), school_changed=False)
    assert next(e for e in m.menu(NOW).entries if e.action == "folder").title == "Ders Notları klasörünü aç"


def test_update_row_only_when_a_new_version_waits():
    from blackboard_sync.updater import CheckResult, Release
    m = model(session=signed_session())
    m.updates.finish_check(CheckResult("available", Release("9.9.9", "", "x.dmg", "")), NOW, manual=False)
    titles = [e.title for e in m.menu(NOW).entries]
    assert titles[-3:] == ["Güncelleme var: 9.9.9 — Güncelle", "Ayarlar…", "Çık"]


def test_expiry_overrides_saved_cookies_and_survives_network_errors():
    m = model(session=signed_session(NOW - timedelta(hours=1)))
    m.finish_sync(RunOutcome("login_required", finished_at=NOW), NOW)
    menu = m.menu(NOW)
    row = menu.entries[0]
    assert row.title == "⚠ Oturum sona erdi — Giriş yap" and row.warning
    assert row.action == "login"
    assert menu.entries[1].title == f"{format_time(NOW, NOW)} denendi · sonraki: {format_time(NOW + SYNC_INTERVAL, NOW)}"
    assert menu.entries[2].title == ""  # still two lines at the top
    status = window_status(m)
    assert status.account_warning and (status.account_title, status.account_action) == ("Giriş yap", "login")
    m.finish_sync(RunOutcome("error", finished_at=NOW), NOW)
    assert m.menu(NOW).entries[0].warning
    m.session = signed_session(NOW + timedelta(minutes=1))
    assert m.menu(NOW).entries[0].title.startswith("✓ Ada Student · ")
    status = window_status(m)
    assert (status.account, status.account_title, status.account_action) == (
        "Giriş yapıldı: Ada Student", "Hesaptan çıkış yap", "logout")


def test_saved_session_without_sync_and_legacy_username():
    m = model(session={"user": {"userName": "student"}})
    assert m.menu(NOW).entries[0].title == "✓ student · henüz senkronize edilmedi"
    assert m.menu(NOW).status_lines[1].startswith("Sonraki: ")
    assert model().menu(NOW).entries[0].action == "login"
    assert model(session_expired=True).menu(NOW).entries[0].warning
    status = window_status(model(configured=False))
    assert (status.account, status.account_title, status.account_action) == ("Henüz giriş yapılmadı.", "Giriş yap", "login")
    assert status.account_enabled and not status.refetch_enabled  # no folder before the first save


def test_syncing_disables_mutating_actions_but_keeps_folders():
    m = model(session=signed_session(), last=outcome())
    assert window_status(m).account_enabled and window_status(m).refetch_enabled
    m.begin("sync")
    menu = m.menu(NOW)
    actions = {e.action: e for e in entries(menu) if e.action}
    assert actions["sync"].title == "Senkronize ediliyor…"
    assert not actions["sync"].enabled
    assert actions["folder"].enabled and actions["settings"].enabled
    assert menu.status_lines == [f"✓ Ada Student · {format_time(NOW, NOW)} senkronize edildi", "Yeni içerik kontrol ediliyor…"]
    status = window_status(m)
    assert not status.account_enabled and not status.refetch_enabled
    assert status.update_enabled  # update checks do not use the job slot


def test_course_counts_reset_on_success_and_survive_errors():
    m = model(last=outcome())
    def courses():
        return next(e.children for e in m.menu(NOW).entries if e.title == "Dersler")
    assert courses()[0].title == "CSE303 (3 yeni)"
    assert courses()[0].value == CSE
    m.finish_sync(RunOutcome("error", finished_at=NOW), NOW)
    assert courses()[0].title == "CSE303 (3 yeni)"
    m.finish_sync(outcome(report(courses=[course("CSE303", CSE)])), NOW)
    assert courses()[0].title == "CSE303"
    m.finish_sync(outcome(report()), NOW)
    assert courses()[0].title == "Henüz ders yok" and not courses()[0].enabled


def test_course_display_name_and_recent_dates():
    data = report(courses=[dict(code="CSE303", name="Algorithm Analysis", folder=CSE, new_files=[f"{CSE}/a.pdf"])])
    m = model()
    m.finish_sync(outcome(data), NOW)
    menu = m.menu(NOW)
    assert next(e for e in menu.entries if e.title == "Dersler").children[0].title == "CSE303 Algorithm Analysis (1 yeni)"
    assert menu.recent[0][0] == f"{NOW.astimezone():%d.%m %H:%M} · CSE303 · a.pdf"


def test_status_line_is_stable_while_time_passes():
    local = datetime(2026, 10, 3, 14, 0).astimezone()
    m = model(last=RunOutcome("ok", finished_at=local))
    first = m.menu(local + timedelta(minutes=5))
    assert first.status_lines[0].startswith("14:00 senkronize edildi · ")
    assert m.menu(local + timedelta(minutes=6)) == first  # no per-minute change, so no rebuild
    m.next_run_at = local + timedelta(minutes=2)  # overdue: no ticking clock either
    overdue = m.menu(local + timedelta(minutes=5))
    assert overdue.status_lines[0].endswith("sonraki: birazdan")
    assert m.menu(local + timedelta(minutes=6)) == overdue
    assert m.menu(local + timedelta(days=1)).status_lines[0].startswith("Dün 14:00 senkronize edildi · ")

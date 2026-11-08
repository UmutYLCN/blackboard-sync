"""The Settings page as data: which sections and rows it has, and what changes while the app runs."""

from dataclasses import fields

from blackboard_sync import uninstall
from blackboard_sync.gcal import CalendarStatus
from blackboard_sync.menubar import settings_form as f
from blackboard_sync.menubar.settings_form import (
    CONTROL_BUTTON,
    CONTROL_FIELD,
    CONTROL_POPUP,
    CONTROL_SWITCH,
    SECTION_ACCOUNT,
    SECTION_APPEARANCE,
    SECTION_CALENDAR,
    SECTION_DANGER,
    SECTION_FOLDER,
    SECTION_ORDER,
    SECTION_SYNC,
    SECTION_UPDATES,
    SECTIONS,
    FormValues,
    WindowStatus,
    row_states,
    settings_sections,
)
from blackboard_sync.menubar.settings_form import SECTION_NOTEBOOKLM


def test_only_the_macos_window_has_the_notebooklm_section():
    assert SECTION_NOTEBOOKLM not in [section.key for section in settings_sections(appearance=True)]
    section = next(s for s in settings_sections(notebooklm=True) if s.key == SECTION_NOTEBOOKLM)
    assert [row.key for row in section.rows] == ["notebooklm_auto", "notebooklm_duplicates", "notebooklm_disconnect"]
    assert section.rows[0].title == "Add new files to NotebookLM after each sync"
    assert "unofficial" in section.footer


def all_rows():
    return [row for section in settings_sections(notebooklm=True, auto_relogin=True) for row in section.rows]


def test_the_sections_come_in_the_planned_order_with_a_slot_for_the_calendar():
    assert SECTION_ORDER == (SECTION_ACCOUNT, SECTION_SYNC, SECTION_APPEARANCE, SECTION_CALENDAR, SECTION_NOTEBOOKLM,
                             SECTION_FOLDER, SECTION_UPDATES, SECTION_DANGER)
    # The immediate Calendar controls occupy the reserved slot.
    assert SECTION_CALENDAR in SECTIONS
    assert [section.key for section in settings_sections()] == [
        SECTION_ACCOUNT, SECTION_SYNC, SECTION_CALENDAR, SECTION_FOLDER, SECTION_UPDATES, SECTION_DANGER]
    assert [section.title for section in settings_sections()] == [
        "Account", "Sync", "Google Calendar", "Folder", "Updates", "Danger zone"]
    # Appearance (the theme) only where the window can change it: the Windows WebView2 window.
    assert [section.key for section in settings_sections(appearance=True)][:4] == [
        SECTION_ACCOUNT, SECTION_SYNC, SECTION_APPEARANCE, SECTION_CALENDAR]
    assert [row.key for row in SECTIONS[SECTION_APPEARANCE].rows] == ["theme"]


def test_the_rows_of_each_section():
    rows = {section.key: [row.key for row in section.rows] for section in settings_sections()}
    assert rows == {
        SECTION_ACCOUNT: ["base_url", "account"],
        SECTION_SYNC: ["interval", "autostart", "language"],
        SECTION_CALENDAR: ["google_calendar", "google_calendar_sync", "google_calendar_disconnect"],
        SECTION_FOLDER: ["dest"],
        SECTION_UPDATES: ["check_updates", "update"],
        SECTION_DANGER: ["uninstall"],
    }
    assert len({row.key for row in all_rows()}) == len(all_rows())  # keys name the controls


def test_every_form_value_has_exactly_one_row_and_no_setting_is_invented():
    edited = [row.field for row in all_rows() if row.field]
    # The form's own values: the school, folder, login item, update checks, interval, language, re-sign-in.
    assert sorted(edited) == sorted(field.name for field in fields(FormValues))
    assert len(edited) == len(set(edited))


def test_controls_match_what_they_edit():
    by_field = {row.field: row for row in all_rows() if row.field}
    assert by_field["base_url"].control == CONTROL_FIELD and by_field["dest"].control == CONTROL_FIELD
    assert by_field["dest"].button == "Choose…"  # the folder picker beside the path
    assert by_field["autostart"].control == by_field["check_updates"].control == CONTROL_SWITCH
    assert by_field["sync_interval_minutes"].control == by_field["language"].control == CONTROL_POPUP
    # What acts at once (or only chooses) has no field, so Save and Cancel never touch it.
    immediate = {row.key: row.control for row in all_rows() if not row.field}
    assert immediate == {"account": CONTROL_BUTTON, "update": CONTROL_BUTTON, "uninstall": CONTROL_BUTTON,
                         "google_calendar": CONTROL_BUTTON, "google_calendar_sync": CONTROL_BUTTON,
                         "google_calendar_disconnect": CONTROL_BUTTON, "notebooklm_disconnect": CONTROL_BUTTON,
                         "notebooklm_duplicates": CONTROL_BUTTON}


def test_every_row_has_a_description_or_a_live_one():
    live = {"account", "update", "google_calendar"}  # the status supplies their text
    for row in all_rows():
        assert row.title or row.key in live, row.key
        if row.key not in live:
            assert row.detail or row.control in (CONTROL_BUTTON,), row.key


def test_the_uninstall_row_is_the_only_destructive_one_and_it_is_last():
    assert [row.key for row in all_rows() if row.destructive] == ["uninstall"]
    assert [section.key for section in settings_sections() if section.danger] == [SECTION_DANGER]
    assert settings_sections()[-1].key == SECTION_DANGER
    row = SECTIONS[SECTION_DANGER].rows[0]
    assert (row.title, row.detail, row.button) == ("Uninstall Blackboard Sync", uninstall.MESSAGE, "Uninstall app…")


def test_the_folder_note_and_the_hint_say_what_they_said_before():
    assert SECTIONS[SECTION_FOLDER].rows[0].detail == f.T_DEST_ROOT_NOTE
    assert SECTIONS[SECTION_FOLDER].footer == f.T_DEST_CHANGE_NOTE
    assert f.T_DEST_HINT == f"{f.T_DEST_ROOT_NOTE} {f.T_DEST_CHANGE_NOTE}"  # the Windows page still shows both in one


def status(**kwargs):
    values = dict(account="Signed in as Ada", account_warning=False, account_title="Sign out", account_action="logout",
                  account_enabled=True, version="Version 1.5.5", update_title="Check now", update_action="check_updates",
                  update_enabled=True)
    values.update(kwargs)
    return WindowStatus(**values)


def test_account_row_follows_who_is_signed_in():
    state = row_states(status())["account"]
    assert (state.title, state.button, state.enabled, state.warning) == ("Signed in as Ada", "Sign out", True, False)
    expired = row_states(status(account="Your session expired; sign in again.", account_warning=True,
                                account_title="Sign in", account_enabled=False))["account"]
    assert (expired.title, expired.button, expired.enabled, expired.warning) == (
        "Your session expired; sign in again.", "Sign in", False, True)


def test_update_and_uninstall_rows():
    states = row_states(status(update_title="Update to 1.6.0", update_enabled=False, uninstall_enabled=True))
    assert (states["update"].title, states["update"].button, states["update"].enabled) == (
        "Version 1.5.5", "Update to 1.6.0", False)
    assert states["uninstall"].enabled
    assert not row_states(status())["uninstall"].enabled  # a sync or sign-in holds the job slot


def calendar_row(calendar, **kwargs):
    return row_states(status(calendar=calendar, **kwargs))["google_calendar"]


def test_calendar_card_after_a_cancelled_or_timed_out_connect_is_not_connected():
    # Nothing is stored for a connect that did not finish, so the saved status is the plain one.
    plain = f.calendar_presentation(CalendarStatus())
    assert (plain.title, plain.button, plain.warning, plain.show_connect) == (
        "Not connected", "Connect Google Calendar", False, True)
    assert not plain.show_sync and not plain.show_disconnect
    state = calendar_row(CalendarStatus())
    assert (state.title, state.button, state.enabled, state.warning) == (
        "Not connected", "Connect Google Calendar", True, False)
    # An error left behind by an older version does not turn the card into an error card.
    stale = f.calendar_presentation(CalendarStatus(False, last_error="Google Calendar authorization timed out."))
    assert (stale.title, stale.warning, stale.button) == ("Not connected", False, "Connect Google Calendar")


def test_the_notice_replaces_only_the_explanation_for_a_moment():
    notice = "Google Calendar authorization timed out."
    shown = f.calendar_presentation(CalendarStatus(), notice=notice)
    assert (shown.title, shown.detail, shown.button, shown.warning) == (
        "Not connected", notice, "Connect Google Calendar", False)
    assert f.calendar_presentation(CalendarStatus()).detail == "Connect to see Blackboard deadlines in Google Calendar."
    assert calendar_row(CalendarStatus(), calendar_notice=notice).detail == notice
    # While a connect is running the card is about that, not about the last attempt.
    busy = f.calendar_presentation(CalendarStatus(), "connect", notice=notice)
    assert busy.title == "Google Calendar operation in progress…" and busy.detail != notice


def test_calendar_card_when_connected():
    shown = f.calendar_presentation(CalendarStatus(True, last_sync="2026-10-18T10:00:00+00:00"))
    assert (shown.title, shown.warning, shown.show_connect, shown.show_sync, shown.show_disconnect) == (
        "Connected", False, False, True, True)


def test_calendar_card_keeps_the_error_when_a_connected_sync_fails():
    shown = f.calendar_presentation(CalendarStatus(True, last_error="Google Calendar sync failed."))
    assert (shown.title, shown.detail, shown.button, shown.warning) == (
        "Google Calendar error", "Google Calendar sync failed.", "Reconnect", True)
    assert shown.show_connect and shown.show_disconnect and not shown.show_sync


def test_calendar_card_when_it_needs_a_reconnect():
    shown = f.calendar_presentation(
        CalendarStatus(True, last_error="Google Calendar needs to be reconnected", needs_reconnect=True))
    assert (shown.title, shown.button, shown.warning) == (
        "Google Calendar needs to be reconnected", "Reconnect", True)
    assert shown.show_connect and shown.show_disconnect and not shown.sync_enabled

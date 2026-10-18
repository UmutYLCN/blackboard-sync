"""The Settings page as data: which sections and rows it has, and what changes while the app runs."""

from dataclasses import fields

from blackboard_sync import uninstall
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
    SECTION_PAST_TERMS,
    SECTION_SYNC,
    SECTION_UPDATES,
    SECTIONS,
    FormValues,
    WindowStatus,
    row_states,
    settings_sections,
)


def all_rows():
    return [row for section in settings_sections() for row in section.rows]


def test_the_sections_come_in_the_planned_order_with_a_slot_for_the_calendar():
    assert SECTION_ORDER == (SECTION_ACCOUNT, SECTION_SYNC, SECTION_APPEARANCE, SECTION_CALENDAR, SECTION_FOLDER,
                             SECTION_PAST_TERMS, SECTION_UPDATES, SECTION_DANGER)
    # The immediate Calendar controls occupy the reserved slot.
    assert SECTION_CALENDAR in SECTIONS
    assert [section.key for section in settings_sections()] == [
        SECTION_ACCOUNT, SECTION_SYNC, SECTION_CALENDAR, SECTION_FOLDER, SECTION_PAST_TERMS, SECTION_UPDATES, SECTION_DANGER]
    assert [section.title for section in settings_sections()] == [
        "Account", "Sync", "Google Calendar", "Folder", "Past terms", "Updates", "Danger zone"]
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
        SECTION_PAST_TERMS: ["past_term", "past_download"],
        SECTION_UPDATES: ["check_updates", "update"],
        SECTION_DANGER: ["uninstall"],
    }
    assert len({row.key for row in all_rows()}) == len(all_rows())  # keys name the controls


def test_every_form_value_has_exactly_one_row_and_no_setting_is_invented():
    edited = [row.field for row in all_rows() if row.field]
    # The form's own values: the school, folder, login item, update checks, interval and language.
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
    assert immediate == {"account": CONTROL_BUTTON, "past_term": CONTROL_POPUP, "past_download": CONTROL_BUTTON,
                         "update": CONTROL_BUTTON, "uninstall": CONTROL_BUTTON,
                         "google_calendar": CONTROL_BUTTON, "google_calendar_sync": CONTROL_BUTTON,
                         "google_calendar_disconnect": CONTROL_BUTTON}


def test_every_row_has_a_description_or_a_live_one():
    live = {"account", "update", "past_download", "google_calendar"}  # the status supplies their text
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
    values = dict(past_available=True, account="Signed in as Ada", account_warning=False, account_title="Sign out", account_action="logout",
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


def test_past_term_rows_follow_the_download():
    idle = row_states(status(past_terms=("2025-2026 Bahar",), past_message="", past_enabled=True))
    assert idle["past_term"].enabled
    assert (idle["past_download"].button, idle["past_download"].enabled, idle["past_download"].running) == (
        "Download past term", True, False)
    running = row_states(status(past_terms=("2025-2026 Bahar",), past_message="Downloading…", past_running=True))
    assert not running["past_term"].enabled  # the list is locked while a term downloads
    assert (running["past_download"].button, running["past_download"].detail, running["past_download"].running) == (
        "Downloading…", "Downloading…", True)
    empty = row_states(status(past_message="Sign in to see past terms."))
    assert not empty["past_term"].enabled and not empty["past_download"].enabled
    assert empty["past_download"].detail == "Sign in to see past terms."
    # Rows without live text keep the definition's.
    assert row_states(status())["past_term"].title is None and row_states(status())["past_term"].detail is None

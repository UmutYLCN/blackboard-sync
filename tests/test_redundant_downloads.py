"""Unchanged attachments are not downloaded again (audit R2/R3)."""

from __future__ import annotations

from .test_sync import CSE, SLIDES, SYLLABUS, SYLLABUS_DL, files_under, sync
from .test_sync import _route_item

HOMEWORK_DL = "/learn/api/public/v1/courses/_13004_1/contents/_c4_1/attachments/_a41_1/download"


def _bad_sibling(fake_bb):
    fake_bb.routes["/learn/api/public/v1/courses/_13004_1/contents/_c11_1/attachments"]["results"].append(
        {"id": "_bad_1", "fileName": "missing.pdf"}
    )


def test_R3_failing_attachment_does_not_redownload_its_siblings(config, client, fake_bb):
    _bad_sibling(fake_bb)
    first = sync(config, client)
    assert SYLLABUS_DL in fake_bb.downloads()
    print(first.warnings, [c.warnings for c in first.courses])
    assert any("Skipped" in w for c in first.courses for w in c.warnings)
    for _ in range(2):
        fake_bb.calls.clear()
        sync(config, client)
        assert SYLLABUS_DL not in fake_bb.downloads()
        # the failed attachment is still retried every run
        assert any(c.endswith("/_bad_1/download") for c in fake_bb.calls)
    assert SYLLABUS in files_under(config.dest)


def test_R3_failed_attachment_is_fetched_once_it_recovers(config, client, fake_bb):
    _bad_sibling(fake_bb)
    sync(config, client)
    fake_bb.files["/learn/api/public/v1/courses/_13004_1/contents/_c11_1/attachments/_bad_1/download"] = b"%PDF late"
    fake_bb.calls.clear()
    report = sync(config, client)
    assert report.totals()["new_files"] == 1
    assert SYLLABUS_DL not in fake_bb.downloads()
    # now complete: the item is skipped outright
    fake_bb.calls.clear()
    sync(config, client)
    assert fake_bb.downloads() == []


def test_R3_partial_item_still_redownloads_when_the_item_changed_or_file_is_gone(config, client, fake_bb):
    _bad_sibling(fake_bb)
    sync(config, client)
    (config.dest / SYLLABUS).unlink()
    fake_bb.calls.clear()
    sync(config, client)
    assert SYLLABUS_DL in fake_bb.downloads()  # the local copy vanished, so fetch it again
    _route_item(fake_bb, "_c11_1")["modified"] = "2026-10-01T00:00:00.000Z"
    fake_bb.files[SYLLABUS_DL] = b"%PDF syllabus v2"
    fake_bb.calls.clear()
    report = sync(config, client)
    assert SYLLABUS_DL in fake_bb.downloads() and report.totals()["updated_files"] == 1


def test_R2_item_without_modified_skips_unchanged_bodies(config, client, fake_bb):
    fake_bb.etags[SYLLABUS_DL] = '"v1"'
    _route_item(fake_bb, "_c11_1").pop("modified")
    sync(config, client)
    for _ in range(2):
        fake_bb.calls.clear()
        fake_bb.conditional_requests.clear()
        report = sync(config, client)
        assert fake_bb.conditional_requests == [SYLLABUS_DL]
        assert report.totals()["new_files"] == 0 and report.totals()["updated_files"] == 0
    assert (config.dest / SYLLABUS).read_bytes() == b"%PDF syllabus v1"


def test_R2_changed_content_is_downloaded_even_if_validators_are_reused(config, client, fake_bb):
    fake_bb.etags[SYLLABUS_DL] = '"v1"'
    _route_item(fake_bb, "_c11_1").pop("modified")
    sync(config, client)
    fake_bb.files[SYLLABUS_DL] = b"%PDF syllabus v2!"
    fake_bb.etags[SYLLABUS_DL] = '"v2"'
    report = sync(config, client)
    assert report.totals()["updated_files"] == 1
    assert (config.dest / SYLLABUS).read_bytes() == b"%PDF syllabus v2!"


def test_R2_etag_match_but_different_length_is_downloaded(config, client, fake_bb):
    fake_bb.etags[SYLLABUS_DL] = '"same"'
    _route_item(fake_bb, "_c11_1").pop("modified")
    sync(config, client)
    fake_bb.files[SYLLABUS_DL] = b"%PDF a much longer replacement body"
    # a server that ignores If-None-Match and keeps the ETag while the length changes
    fake_bb.ignore_conditional = True
    report = sync(config, client)
    assert report.totals()["updated_files"] == 1


def test_description_only_edit_does_not_redownload_attachments(config, client, fake_bb):
    fake_bb.etags[SYLLABUS_DL] = '"v1"'
    sync(config, client)
    _route_item(fake_bb, "_c11_1")["modified"] = "2026-10-01T00:00:00.000Z"
    fake_bb.calls.clear()
    report = sync(config, client)
    assert report.totals()["updated_files"] == 0
    assert fake_bb.conditional_requests.count(SYLLABUS_DL) == 1


def test_without_validators_the_file_is_still_downloaded_and_compared(config, client, fake_bb):
    _route_item(fake_bb, "_c11_1").pop("modified")
    sync(config, client)
    fake_bb.calls.clear()
    sync(config, client)
    assert SYLLABUS_DL in fake_bb.downloads()

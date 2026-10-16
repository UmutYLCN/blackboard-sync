"""One odd page must not stop a sync, and two items sharing a file id each get their file."""

from html.parser import HTMLParser

from blackboard_sync import htmltext
from blackboard_sync.api import BlackboardClient
from blackboard_sync.config import Config
from blackboard_sync.state import State

from .conftest import BASE_URL, SAMPLE_FILES, FakeBlackboard, load_routes
from .test_sync import CSE, files_under, sync

CONTENTS = "/learn/api/public/v1/courses/_13004_1/contents"
REJECTED = "<p>hi</p><![foo[ bar ]]><p>after</p>"


class Strict(HTMLParser):
    """Like Python before the parser fix: a marked section raises AssertionError."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text = []

    def handle_data(self, data):
        self.text.append(data)

    def feed(self, data):
        if "<![foo[" in data:
            raise AssertionError("unknown status keyword 'foo' in marked section")
        super().feed(data)


def test_feed_html_drops_markup_the_parser_rejects():
    parser = htmltext.feed_html(Strict, REJECTED)
    assert "".join(parser.text) == "hiafter"


def test_feed_html_falls_back_to_plain_text_when_nothing_else_helps():
    class Never(Strict):
        def feed(self, data):
            if "<" in data:
                raise AssertionError("no tags at all")
            super().feed(data)

    assert "hi" in "".join(htmltext.feed_html(Never, "<b>hi</b>").text)


def test_a_rejected_body_does_not_stop_the_sync(tmp_path, monkeypatch):
    monkeypatch.setattr(htmltext, "_Converter", _rejecting(htmltext._Converter))
    monkeypatch.setattr(htmltext, "_EmbedFinder", _rejecting(htmltext._EmbedFinder))
    routes = load_routes()
    routes[CONTENTS]["results"].insert(0, {
        "id": "_bad_1", "title": "Pasted from Word", "position": -1, "modified": "2026-09-01T10:00:00.000Z",
        "contentHandler": {"id": "resource/x-bb-document"}, "body": REJECTED})
    routes[f"{CONTENTS}/_bad_1/attachments"] = {"results": []}
    config = Config(base_url=BASE_URL, dest=tmp_path / "University", data_dir=tmp_path / "data")

    report = sync(config, BlackboardClient(BASE_URL, FakeBlackboard(routes, dict(SAMPLE_FILES))))

    assert report.status == "ok"
    assert any(f.endswith("Pasted from Word.pdf") for f in files_under(config.root))
    assert any(f.endswith("hw1.pdf") for f in files_under(config.root))  # the rest of the course came too


def _rejecting(parser_class):
    class Rejecting(parser_class):
        def feed(self, data):
            if "<![foo[" in data:
                raise AssertionError("unknown status keyword 'foo' in marked section")
            super().feed(data)

    return Rejecting


def _shared_file_setup(tmp_path):
    routes = load_routes()
    routes[CONTENTS]["results"] = [
        {"id": f"_x{i}_1", "title": f"Copy {i}", "position": i, "modified": "2026-09-01T10:00:00.000Z",
         "contentHandler": {"id": "resource/x-bb-file"}} for i in (1, 2)
    ]
    files = {}
    for i in (1, 2):
        routes[f"{CONTENTS}/_x{i}_1/attachments"] = {"results": [{"id": "_shared_1", "fileName": f"x{i}.pdf"}]}
        files[f"{CONTENTS}/_x{i}_1/attachments/_shared_1/download"] = b"SAME BYTES"
    config = Config(base_url=BASE_URL, dest=tmp_path / "University", data_dir=tmp_path / "data")
    return config, BlackboardClient(BASE_URL, FakeBlackboard(routes, files))


def test_two_items_sharing_a_file_id_each_get_their_file(tmp_path):
    config, client = _shared_file_setup(tmp_path)

    sync(config, client)

    pdfs = [f for f in files_under(config.root) if f.startswith(CSE) and f.endswith((".pdf",)) and "/x" in f]
    assert sorted(p.rsplit("/", 1)[1] for p in pdfs) == ["x1.pdf", "x2.pdf"]
    outputs = State.load(config.state_file).outputs
    assert "attachment:_13004_1:_shared_1" in outputs  # the first keeps the usual key
    assert "attachment:_13004_1:_x2_1:_shared_1" in outputs


def test_shared_file_ids_stay_stable_and_nothing_is_downloaded_again(tmp_path):
    config, client = _shared_file_setup(tmp_path)
    sync(config, client)
    before = files_under(config.root)
    downloads = len(client.http.downloads())

    report = sync(config, client)

    assert files_under(config.root) == before
    assert len(client.http.downloads()) == downloads
    assert report.totals()["new_files"] == 0

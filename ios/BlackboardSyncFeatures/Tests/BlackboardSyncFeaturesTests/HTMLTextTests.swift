import XCTest
@testable import BlackboardSyncFeatures

/// The desktop's `tests/test_notes.py` cases for `htmltext.py`, plus the tokenizer's edges.
final class HTMLTextTests: XCTestCase {
    func testMarkdownBasicFormatting() {
        let html = "<h2>Exam</h2><p>The exam is on <strong>Friday</strong> in <em>room 101</em>.</p>"
            + "<ul><li>Bring ID</li><li>No phones</li></ul>"
            + "<p>Details: <a href=\"https://example.org/exam\">exam page</a></p>"
            + "<p><a href=\"https://example.org/raw\">https://example.org/raw</a></p>"
        XCTAssertEqual(HTMLText.markdown(html), """
        ## Exam

        The exam is on **Friday** in _room 101_.

        - Bring ID
        - No phones

        Details: [exam page](https://example.org/exam)

        <https://example.org/raw>
        """)
    }

    func testOrderedListBreaksAndEntities() {
        let html = "<ol><li>One</li><li>Two &amp; three</li></ol><p>a<br>b</p><p><strong></strong></p>"
        XCTAssertEqual(HTMLText.markdown(html), "1. One\n2. Two & three\n\na\nb")
    }

    func testPlainTextPassesThrough() {
        XCTAssertEqual(HTMLText.markdown("just text"), "just text")
        XCTAssertEqual(HTMLText.markdown(""), "")
        XCTAssertEqual(HTMLText.markdown("  plain &amp; simple "), "plain & simple")
    }

    func testNestedListsSitUnderTheirParentText() {
        let html = "<ul><li>Part A<ol><li>Read</li><li>Write<ul><li>Short</li></ul></li></ol></li></ul>"
            + "<ol>" + String(repeating: "<li>x</li>", count: 9) + "<li>Ten<ul><li>Nested</li></ul></li></ol>"
        let numbered = (1...9).map { "\($0). x\n" }.joined()
        XCTAssertEqual(HTMLText.markdown(html),
                       "- Part A\n  1. Read\n  2. Write\n     - Short\n\n" + numbered + "10. Ten\n    - Nested")
    }

    func testBoldKeepsItsMarkerOnTheWord() {
        XCTAssertEqual(HTMLText.markdown("<p><b>Note: </b>bring a pen</p>"), "**Note:** bring a pen")
    }

    func testFileLinksAreLeftOutOfTheText() {
        let html = #"<p>See <a href="/bbcswebdav/xid-1_1" data-bbfile="{&quot;linkName&quot;:&quot;a.pdf&quot;}">a.pdf</a> now</p>"#
        XCTAssertEqual(HTMLText.markdown(html), "See now")
    }

    func testScriptsStylesAndCommentsAreHidden() {
        let html = "<style>p{color:red}</style><script>alert('<p>x</p>')</script><!-- note --><p>Shown</p>"
        XCTAssertEqual(HTMLText.markdown(html), "Shown")
        XCTAssertEqual(HTMLText.plainText(html), "Shown")
    }

    func testOddMarkupNeverFails() {
        // A marked section stopped Python's parser once (`feed_html`); here it is skipped.
        XCTAssertEqual(HTMLText.plainText("<![foo[<p>Text</p>"), "Text")
        XCTAssertEqual(HTMLText.plainText("a < b and <p>c"), "a < b and c")
        XCTAssertEqual(HTMLText.markdown("<p>unclosed <strong>bold"), "unclosed **bold")
        XCTAssertEqual(HTMLText.plainText("<p title='x>y'>ok</p><br/>"), "ok")
    }

    func testPlainTextPreviewCollapsesBlocksAndDecodesEntities() {
        XCTAssertEqual(HTMLText.plainText("<p>Exam <strong>rooms</strong> &amp; times.</p><p>Be early.</p>"),
                       "Exam rooms & times. Be early.")
        XCTAssertEqual(HTMLText.plainText("<div>a</div><div>b&nbsp;&nbsp;c</div><ul><li>d</li></ul>"), "a b c d")
        XCTAssertEqual(HTMLText.plainText("&#351;&#x131;&ccedil;&Uuml;&amp&unknown;"), "şıçÜ&&unknown;")
    }

    func testBodyAcceptsRichTextObjects() throws {
        XCTAssertEqual(HTMLText.bodyHTML(try json(#"{"rawText": "<p>x</p>", "displayText": "<p>y</p>"}"#)), "<p>x</p>")
        XCTAssertEqual(HTMLText.bodyHTML(try json(#"{"rawText": "", "displayText": "<p>y</p>"}"#)), "<p>y</p>")
        XCTAssertEqual(HTMLText.bodyHTML(try json(#""<p>z</p>""#)), "<p>z</p>")
        XCTAssertEqual(HTMLText.bodyHTML(nil), "")
        XCTAssertEqual(HTMLText.bodyHTML(.null), "")
    }

    func testEmbeddedFilesReadBbfileMetadata() {
        let html = #"<a href="https://bb.example.edu/bbcswebdav/xid-12_1" "#
            + #"data-bbfile="{&quot;linkName&quot;:&quot;slides.pdf&quot;}">click</a>"#
            + #"<img src="https://bb.example.edu/bbcswebdav/xid-13_1" alt="diagram.png">"#
            + #"<a href="https://bb.example.edu/bbcswebdav/xid-12_1">dup</a>"#
        XCTAssertEqual(EmbeddedFile.find(in: html).map { [$0.xid, $0.name] },
                       [["12_1", "slides.pdf"], ["13_1", "diagram.png"]])
    }

    func testEmbeddedFilePrefersPermanentLinkOverSessionResource() {
        let resource = "https://bb.example.edu/sessions/AA/SESSION/abcdef0123456789abcdef0123456789/guide.pdf?token=FIRST"
        let permanent = "https://bb.example.edu/bbcswebdav/pid-700-dt-asiobject-rid-14_1/xid-14_1?token=SECOND"
        let meta = "{&quot;resourceUrl&quot;: &quot;\(resource)&quot;, &quot;displayName&quot;: &quot;guide.pdf&quot;}"
        let files = EmbeddedFile.find(in: "<a data-bbfile=\"\(meta)\" href=\"\(permanent)\">Guide</a>")
        XCTAssertEqual(files, [EmbeddedFile(xid: "14_1", name: "guide.pdf", url: permanent)])
        XCTAssertEqual(files[0].link(base: base)?.absoluteString,
                       "https://blackboard.example.edu/bbcswebdav/xid-14_1")
    }

    func testSessionUploadsNeedFileMetadata() {
        let url = "/sessions/AA/SESSION/abcdef0123456789abcdef0123456789/guide.pdf"
        XCTAssertEqual(EmbeddedFile.find(in: "<a href=\"\(url)\">Ordinary link</a>"), [])
        let meta = "{&quot;displayName&quot;: &quot;guide.pdf&quot;}"
        let upload = EmbeddedFile.find(in: "<a data-bbfile=\"\(meta)\" href=\"\(url)\">Guide</a>")
        XCTAssertEqual(upload.map(\.xid), ["upload-abcdef0123456789abcdef0123456789"])
        XCTAssertEqual(upload[0].link(base: base)?.absoluteString, "https://blackboard.example.edu" + url)
    }

    func testMediaIsRecognisedByTypeOrName() {
        XCTAssertTrue(EmbeddedFile(xid: "1_1", name: "Lecture.MP4", url: "").isMedia)
        XCTAssertTrue(EmbeddedFile(xid: "1_1", name: "recording", url: "", mime: "audio/mpeg").isMedia)
        XCTAssertFalse(EmbeddedFile(xid: "1_1", name: "slides.pdf", url: "", mime: "application/pdf").isMedia)
    }

    func testLinksStayOnHTTP() {
        XCTAssertNil(Links.resolve("javascript:alert(1)", base: base))
        XCTAssertNil(Links.resolve("file:///private/file", base: base))
        XCTAssertEqual(Links.resolve("/ultra/courses/_1_1/grades", base: URL(string: "https://bb.edu/sub")!)?.absoluteString,
                       "https://bb.edu/sub/ultra/courses/_1_1/grades")
    }
}

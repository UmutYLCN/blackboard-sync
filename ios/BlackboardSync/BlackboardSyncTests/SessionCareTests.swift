import XCTest
import BlackboardSyncFeatures
import WebKit
@testable import BlackboardSync

private let tenant = URL(string: "https://school.example.edu")!
private let announcementsPath = "/learn/api/public/v1/courses/_1_1/announcements?limit=100"

private func cookie(_ name: String = "BbRouter", _ value: String = "x", domain: String = "school.example.edu") -> HTTPCookie {
    HTTPCookie(properties: [.name: name, .value: value, .domain: domain, .path: "/"])!
}

/// A `BbRouter` cookie whose session ends this many seconds from now.
private func router(endingIn seconds: TimeInterval) -> HTTPCookie {
    cookie("BbRouter", "id:1,expires:\(Int(Date().timeIntervalSince1970 + seconds)),signature:abc")
}

final class SessionCareRulesTests: XCTestCase {
    private let now = Date(timeIntervalSince1970: 1_800_000_000)

    func testFollowsTheMacsTimes() {
        XCTAssertEqual(SessionCare.silentTimeout, 20)
        XCTAssertEqual(SessionCare.stillnessTimeout, 6)
        XCTAssertEqual(SessionCare.keepAliveEvery, 25 * 60)
        XCTAssertEqual(SessionCare.expiryMargin, 30 * 60)
        XCTAssertEqual(SessionCare.failedRetryAfter, 10 * 60)
    }

    func testKeepAliveDueEveryTwentyFiveMinutes() {
        var care = SessionCare()
        XCTAssertTrue(care.keepAliveDue(now))
        care.checkedAt = now
        XCTAssertFalse(care.keepAliveDue(now.addingTimeInterval(24 * 60)))
        XCTAssertTrue(care.keepAliveDue(now.addingTimeInterval(25 * 60)))
        XCTAssertTrue(care.keepAliveDue(now.addingTimeInterval(-60)), "the clock was changed: look anyway")
    }

    func testAtMostOneAttemptPerTenMinutesAfterAFailure() {
        var care = SessionCare()
        XCTAssertTrue(care.mayRefresh(now))
        care.record(.needsInteraction, now: now)
        XCTAssertFalse(care.mayRefresh(now.addingTimeInterval(9 * 60)))
        XCTAssertTrue(care.mayRefresh(now.addingTimeInterval(10 * 60)))
        XCTAssertTrue(care.mayRefresh(now.addingTimeInterval(-60)), "the clock was changed")
    }

    func testACancelledAttemptSaysNothingAboutTheSignOn() {
        var care = SessionCare()
        care.record(.cancelled, now: now)
        XCTAssertNil(care.failedAt)
        XCTAssertTrue(care.mayRefresh(now))
    }

    func testSuccessClearsTheFailureAndShowsTheNoteForAWhile() {
        var care = SessionCare()
        care.record(.timedOut, now: now)
        XCTAssertFalse(care.noteVisible(now))
        care.record(.refreshed, now: now)
        XCTAssertNil(care.failedAt)
        XCTAssertTrue(care.noteVisible(now.addingTimeInterval(60)))
        XCTAssertFalse(care.noteVisible(now.addingTimeInterval(SessionCare.noteFor)))
    }

    func testNoSecondAttemptRightAfterOneThatWorked() {
        var care = SessionCare()
        care.record(.refreshed, now: now)
        XCTAssertFalse(care.mayRefresh(now.addingTimeInterval(59)))
        XCTAssertTrue(care.mayRefresh(now.addingTimeInterval(60)))
    }

    func testRefreshOnlyUnderThirtyMinutesLeft() {
        var care = SessionCare()
        care.checkedAt = now
        XCTAssertEqual(care.action(now: now, expiresAt: now.addingTimeInterval(31 * 60)), .nothing)
        XCTAssertEqual(care.action(now: now, expiresAt: now.addingTimeInterval(29 * 60)), .refresh)
        XCTAssertEqual(care.action(now: now, expiresAt: now.addingTimeInterval(-60)), .refresh)
        XCTAssertEqual(care.action(now: now, expiresAt: nil), .nothing)
        care.checkedAt = nil
        XCTAssertEqual(care.action(now: now, expiresAt: nil), .keepAlive, "no expiry known: only the server can tell")
    }

    func testAfterAFailureOnlyTheKeepAliveGoesOn() {
        var care = SessionCare()
        care.record(.needsInteraction, now: now)
        XCTAssertEqual(care.action(now: now, expiresAt: now), .keepAlive)
        care.checkedAt = now
        XCTAssertEqual(care.action(now: now, expiresAt: now), .nothing)
    }

    func testTheSettingStopsEverything() {
        let care = SessionCare(enabled: false)
        XCTAssertFalse(care.keepAliveDue(now))
        XCTAssertFalse(care.mayRefresh(now))
        XCTAssertEqual(care.action(now: now, expiresAt: now), .nothing)
    }

    func testBackgroundCheckAsTheSessionNearsItsEnd() {
        let care = SessionCare()
        XCTAssertEqual(care.nextBackgroundCheck(now: now, expiresAt: nil), now.addingTimeInterval(25 * 60))
        XCTAssertEqual(care.nextBackgroundCheck(now: now, expiresAt: now.addingTimeInterval(60)), now.addingTimeInterval(25 * 60))
        XCTAssertEqual(care.nextBackgroundCheck(now: now, expiresAt: now.addingTimeInterval(3600)), now.addingTimeInterval(1800))
    }

    func testReadsTheExpiryFromBbRouter() {
        XCTAssertEqual(SessionCare.sessionExpiry([cookie("JSESSIONID"), cookie("BbRouter", "id:1,expires:1800000000,sig:a:b")]),
                       Date(timeIntervalSince1970: 1_800_000_000))
        XCTAssertNil(SessionCare.sessionExpiry([cookie("BbRouter", "id:1,expires:soon")]))
        XCTAssertNil(SessionCare.sessionExpiry([cookie("JSESSIONID", "expires:1800000000")]))
    }

    func testOnlyBlackboardsOwnCookiesAreCleared() {
        let cookies = [cookie("a"), cookie("b", domain: ".school.example.edu"), cookie("sso", domain: ".example.edu"),
                       cookie("idp", domain: "login.example.edu")]
        XCTAssertEqual(SessionCare.blackboardOwned(cookies, tenant: tenant).map(\.name), ["a", "b"])
        XCTAssertEqual(SessionCare.sessionCookies(cookies, tenant: tenant).map(\.name), ["a", "b", "sso"],
                       "saved as interactive sign-in saves them")
    }

    func testTheSettingIsOnByDefaultAndSurvivesRelaunch() throws {
        let suite = "SessionCareTests.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        XCTAssertTrue(SessionCare.saved(in: defaults).enabled)
        SessionCare(enabled: false, failedAt: now).save(in: defaults)
        XCTAssertEqual(SessionCare.saved(in: defaults), SessionCare(enabled: false, failedAt: now))
    }

    func testBackgroundRefreshIsDeclaredForIPadOS() throws {
        let info = try XCTUnwrap(Bundle.main.infoDictionary)
        XCTAssertEqual(info["BGTaskSchedulerPermittedIdentifiers"] as? [String], [SessionCare.backgroundTaskID])
        XCTAssertEqual(info["UIBackgroundModes"] as? [String], ["fetch"])
    }

    func testTurkishCopyMatchesTheMac() {
        XCTAssertEqual(L10n.text("Automatic re-sign-in", language: "tr"), "Otomatik yeniden giriş")
        XCTAssertEqual(L10n.text("Session refreshed automatically", language: "tr"), "Oturum otomatik yenilendi")
        XCTAssertNotNil(L10n.turkish["Keeps your session alive and signs in again in the background when your school allows it. Your password is never stored."])
    }
}

@MainActor
private final class FakePage: SilentPage {
    var events: [String] = []
    var pageCookies: () -> [HTTPCookie] = { [] }
    var student = false
    var host: String?
    var currentURL: URL?
    var summary: String = ""
    var failure: SilentOutcome?

    var url: URL? { currentURL ?? host.flatMap { URL(string: "https://\($0)") } }
    var contentSummary: String { summary }

    func open(_ tenant: URL) async { events.append("open") }
    func cookies() async -> [HTTPCookie] { pageCookies() }
    func wantsStudent() -> Bool { student }
    func close() { events.append("close") }
}

@MainActor
final class SilentAttemptTests: XCTestCase {
    private var page: FakePage!
    private var clock = Date(timeIntervalSince1970: 1_800_000_000)
    private var accepted: ([HTTPCookie]) -> Bool = { _ in false }
    private var checks = 0

    override func setUp() async throws {
        page = FakePage()
        clock = Date(timeIntervalSince1970: 1_800_000_000)
        accepted = { _ in false }
        checks = 0
    }

    private func attempt(timeout: TimeInterval = 20) async -> SilentResult {
        let signIn = BrowserSilentSignIn(page: { self.page }, check: { [self] _, cookies, left in
            checks += 1
            XCTAssertLessThanOrEqual(left, 10, "one slow answer must not outlast the attempt")
            return accepted(cookies)
        }, now: { [self] in clock }, pause: { [self] in clock.addTimeInterval(1) })
        return await signIn.attempt(tenant: tenant, timeout: timeout)
    }

    func testSucceedsWithTheCookiesTheAccountCheckAccepted() async {
        var ticks = 0
        page.pageCookies = {
            ticks += 1
            return ticks < 3 ? [cookie("anonymous")] : [cookie("BbRouter"), cookie("idp", domain: "login.other.edu")]
        }
        accepted = { $0.map(\.name) == ["BbRouter"] }
        let result = await attempt()
        XCTAssertEqual(result.outcome, .refreshed)
        XCTAssertEqual(result.cookies.map(\.name), ["BbRouter"])
        XCTAssertEqual(page.events, ["open", "close"])
    }

    func testAskingForAPasswordEndsTheAttemptAtOnce() async {
        page.student = true
        page.host = "login.other.edu"
        let result = await attempt()
        XCTAssertEqual(result.outcome, .needsInteraction)
        XCTAssertTrue(result.cookies.isEmpty)
        XCTAssertEqual(page.events, ["open", "close"])
        XCTAssertEqual(clock, Date(timeIntervalSince1970: 1_800_000_000))
    }

    func testStuckOnBlackboardIsATimeoutAfterTheDeadline() async {
        page.host = "school.example.edu"
        var tick = 0
        page.pageCookies = {
            tick += 1
            self.page.summary = "step \(tick)" // changing page avoids stillness trigger
            return [cookie("anonymous")]
        }
        let result = await attempt(timeout: 20)
        XCTAssertEqual(result.outcome, .timedOut)
        XCTAssertEqual(clock, Date(timeIntervalSince1970: 1_800_000_020))
        XCTAssertEqual(checks, 20)
        XCTAssertEqual(page.events, ["open", "close"])
    }

    func testStillnessOnBlackboardEndsWithNeedsInteraction() async {
        page.host = "school.example.edu"
        page.pageCookies = { [cookie("anonymous")] }
        let result = await attempt(timeout: 20)
        XCTAssertEqual(result.outcome, .needsInteraction)
        XCTAssertEqual(clock, Date(timeIntervalSince1970: 1_800_000_006))
    }

    func testStuckAtTheSchoolWantsTheStudent() async {
        page.host = "login.other.edu"
        let outcome = await attempt().outcome
        XCTAssertEqual(outcome, .needsInteraction)
    }

    func testAPageThatCannotGoOnEndsTheAttempt() async {
        page.failure = .unreachable
        let unreachable = await attempt().outcome
        XCTAssertEqual(unreachable, .unreachable)
        page.failure = .webFailed
        let terminated = await attempt().outcome
        XCTAssertEqual(terminated, .webFailed)
    }

    func testCancelledAttemptClosesThePage() async {
        let signIn = BrowserSilentSignIn(page: { self.page }, check: { _, _, _ in false }, now: { Date() }, pause: {})
        let task = Task { @MainActor in await signIn.attempt(tenant: tenant, timeout: 3600) }
        task.cancel()
        let result = await task.value
        XCTAssertEqual(result.outcome, .cancelled)
        XCTAssertEqual(page.events, ["open", "close"])
    }
}

/// The real web view and WebKit, on a data store of its own and no network.
@MainActor
final class WebSilentPageTests: XCTestCase {
    private func page(showing html: String) async throws -> WebSilentPage {
        let page = WebSilentPage(store: .nonPersistent())
        let body = try XCTUnwrap(html.addingPercentEncoding(withAllowedCharacters: .alphanumerics))
        await page.open(try XCTUnwrap(URL(string: "data:text/html," + body)))
        return page
    }

    private func sees(_ html: String) async throws -> Bool {
        let page = try await page(showing: html)
        defer { page.close() }
        for _ in 0..<30 {
            if page.wantsStudent() { return true }
            try await Task.sleep(for: .milliseconds(100))
        }
        return false
    }

    func testSeesAPasswordField() async throws {
        let seen = try await sees("<form><input type=password></form>")
        XCTAssertTrue(seen)
    }

    func testDoesNotCountAHiddenPasswordField() async throws {
        let seen = try await sees("<input type=text style='display:none'><input type=password style='display:none'><input type=password style='visibility:hidden'>")
        XCTAssertFalse(seen)
    }

    func testSeesAnEmailField() async throws {
        let seen = try await sees("<form><input type=email></form>")
        XCTAssertTrue(seen)
    }

    func testClearsBlackboardsCookiesAndLeavesTheSignOns() async throws {
        let store = WKWebsiteDataStore.nonPersistent()
        await store.httpCookieStore.setCookie(cookie("old"))
        await store.httpCookieStore.setCookie(cookie("sso", domain: ".example.edu"))
        let page = WebSilentPage(store: store)
        await page.open(tenant)
        page.close()
        let left = await store.httpCookieStore.allCookies().map(\.name)
        XCTAssertEqual(left, ["sso"])
    }

    func testAnUnreachableSchoolEndsTheAttempt() async throws {
        let page = WebSilentPage(store: .nonPersistent())
        defer { page.close() }
        await page.open(try XCTUnwrap(URL(string: "https://127.0.0.1:59999/")))
        for _ in 0..<100 where page.failure == nil { try await Task.sleep(for: .milliseconds(100)) }
        XCTAssertEqual(page.failure, .unreachable)
    }
}

@MainActor
private final class FakeSilentSignIn: SilentSignIn {
    var result = SilentResult(outcome: .refreshed, cookies: [router(endingIn: 3600)])
    var attempts = 0
    var timeouts: [TimeInterval] = []
    var hold = false
    private var waiting: CheckedContinuation<Void, Never>?

    func attempt(tenant: URL, timeout: TimeInterval) async -> SilentResult {
        attempts += 1
        timeouts.append(timeout)
        if hold { await withCheckedContinuation { waiting = $0 } }
        return result
    }

    func release() { hold = false; waiting?.resume(); waiting = nil }
}

private final class FakeBackgroundTasks: BackgroundScheduling {
    var submitted: [Date] = []
    var cancelled = 0
    var refuse = false
    func submit(earliest: Date) throws {
        if refuse { throw SyncFailure(message: "unavailable") }
        submitted.append(earliest)
    }
    func cancel() { cancelled += 1 }
}

final class SessionCareModelTests: XCTestCase {
    private var saved: [String: Any?] = [:]
    private let keys = ["sessionCare", "paused", "syncOnOpen", "libraryScope"]

    override func setUp() {
        super.setUp()
        for key in keys {
            saved[key] = UserDefaults.standard.object(forKey: key)
            UserDefaults.standard.removeObject(forKey: key)
        }
    }

    override func tearDown() {
        for (key, value) in saved { UserDefaults.standard.set(value ?? nil, forKey: key) }
        super.tearDown()
    }

    private let alive: (String) async throws -> [String: Any] = { _ in ["id": "_1_1", "results": [[String: Any]]()] }
    private let expired: (String) async throws -> [String: Any] = { _ in
        throw SyncFailure(message: "Session expired. Sign in again.", authRequired: true)
    }

    private struct Harness {
        let model: AppModel
        let silent: FakeSilentSignIn
        let tasks: FakeBackgroundTasks
        let vault: Vault
    }

    private final class Vault {
        var saves: [[HTTPCookie]] = []
        var failure: Error?
    }

    /// A signed-in app on fakes.
    @MainActor
    private func harness(cookies: [HTTPCookie] = [], page: @escaping (String) async throws -> [String: Any]) -> Harness {
        let model = AppModel(), silent = FakeSilentSignIn(), tasks = FakeBackgroundTasks(), vault = Vault()
        model.silentSignIn = silent
        model.backgroundTasks = tasks
        model.saveSession = { _, cookies in
            if let failure = vault.failure { throw failure }
            vault.saves.append(cookies)
        }
        model.loadSession = { nil }
        model.install(tenant: tenant, cookies: cookies, pageLoader: page)
        model.hasStoredSession = true
        model.hasSession = true
        model.terms = [Term(id: "t", name: "2026 Fall", start: nil, end: nil,
                            courses: [Course(id: "_1_1", name: "CSE303 Algorithm Analysis", termID: "t", created: nil)])]
        model.selected = ["_1_1"]
        return Harness(model: model, silent: silent, tasks: tasks, vault: vault)
    }

    @MainActor
    private func waitUntil(_ condition: () -> Bool, file: StaticString = #filePath, line: UInt = #line) async {
        let deadline = Date().addingTimeInterval(5)
        while !condition() && Date() < deadline { try? await Task.sleep(for: .milliseconds(10)) }
        XCTAssertTrue(condition(), file: file, line: line)
    }

    @MainActor
    func testKeepAliveAloneWhileTheSessionHasTimeLeft() async {
        var calls: [String] = []
        let h = harness(cookies: [router(endingIn: 3600)]) { [alive] in calls.append($0); return try await alive($0) }
        await h.model.tendSession()
        XCTAssertEqual(calls, [BlackboardAPI.accountPath])
        XCTAssertEqual(h.silent.attempts, 0)
        await h.model.tendSession()
        XCTAssertEqual(calls.count, 1, "not due again for 25 minutes")
    }

    @MainActor
    func testRefreshesNearExpirySavingTheCookiesLikeASignIn() async {
        let h = harness(cookies: [router(endingIn: 600)], page: alive)
        await h.model.tendSession()
        XCTAssertEqual(h.silent.attempts, 1)
        XCTAssertEqual(h.silent.timeouts, [20])
        XCTAssertEqual(h.vault.saves.count, 1)
        XCTAssertTrue(h.model.sessionNoteVisible)
        // The client now has the new session: the next look finds nothing to do.
        await h.model.tendSession()
        XCTAssertEqual(h.silent.attempts, 1)
    }

    @MainActor
    func testAKeepAliveThatFindsTheSessionOverSignsInAgain() async {
        let h = harness(cookies: [cookie("JSESSIONID")], page: expired)
        await h.model.tendSession()
        XCTAssertEqual(h.silent.attempts, 1)
        XCTAssertFalse(h.model.needsSignIn)
        XCTAssertTrue(h.model.hasSession)
    }

    @MainActor
    func testAFailureNearExpiryLeavesAWorkingSessionAlone() async {
        let h = harness(cookies: [router(endingIn: 600)], page: alive)
        h.silent.result = SilentResult(outcome: .needsInteraction)
        await h.model.tendSession()
        XCTAssertEqual(h.silent.attempts, 1)
        XCTAssertFalse(h.model.needsSignIn)
        XCTAssertTrue(h.vault.saves.isEmpty)
        XCTAssertFalse(h.model.sessionNoteVisible)
    }

    @MainActor
    func testFallsBackToSignInWhenTheSessionIsOverAndTheSchoolWantsTheStudent() async {
        let h = harness(cookies: [router(endingIn: -60)], page: expired)
        h.silent.result = SilentResult(outcome: .needsInteraction)
        await h.model.tendSession()
        XCTAssertTrue(h.model.needsSignIn)
        XCTAssertFalse(h.model.hasSession)
        XCTAssertEqual(h.model.status, "Sign-in needed")
    }

    @MainActor
    func testRateLimitedAfterAFailure() async {
        let h = harness(cookies: [router(endingIn: 600)], page: alive)
        h.silent.result = SilentResult(outcome: .timedOut)
        await h.model.tendSession()
        await h.model.tendSession()
        await h.model.tendSession()
        XCTAssertEqual(h.silent.attempts, 1)
        XCTAssertNotNil(h.model.care.failedAt)
        XCTAssertNotNil(SessionCare.saved().failedAt, "survives a relaunch")
    }

    @MainActor
    func testTwoLooksAtOnceRunOneAttempt() async {
        let h = harness(cookies: [router(endingIn: 600)], page: alive)
        h.silent.hold = true
        async let first: Void = h.model.tendSession()
        async let second: Void = h.model.tendSession()
        await waitUntil { h.silent.attempts == 1 }
        try? await Task.sleep(for: .milliseconds(50))
        h.silent.release()
        _ = await (first, second)
        XCTAssertEqual(h.silent.attempts, 1)
        XCTAssertEqual(h.vault.saves.count, 1)
    }

    @MainActor
    func testNoRefreshDuringInteractiveSignInAndNoneLeftRunningWhenItStarts() async {
        let h = harness(cookies: [router(endingIn: 600)], page: alive)
        h.model.showingLogin = true
        await h.model.tendSession()
        XCTAssertEqual(h.silent.attempts, 0)

        h.model.showingLogin = false
        h.silent.hold = true
        let look = Task { await h.model.tendSession() }
        await waitUntil { h.silent.attempts == 1 }
        h.model.tenantText = tenant.absoluteString
        h.model.signIn()
        XCTAssertTrue(h.model.showingLogin)
        h.silent.release()
        await look.value
        XCTAssertTrue(h.vault.saves.isEmpty, "the student's sign-in replaces it")
        XCTAssertFalse(h.model.sessionNoteVisible)
        XCTAssertNil(h.model.care.failedAt, "cancelled is not a failure")
    }

    @MainActor
    func testNothingRunsWhileWorkIsRunningPausedOrSwitchedOff() async {
        var calls = 0
        let h = harness(cookies: [router(endingIn: 600)]) { [alive] in calls += 1; return try await alive($0) }
        h.model.busy = true
        await h.model.tendSession()
        h.model.busy = false
        h.model.togglePause()
        XCTAssertTrue(h.model.paused)
        await h.model.tendSession()
        h.model.togglePause()
        h.model.automaticSignIn = false
        await h.model.tendSession()
        XCTAssertEqual(calls, 0)
        XCTAssertEqual(h.silent.attempts, 0)
    }

    @MainActor
    func testSwitchingTheSettingOffStopsARunningAttemptAndTheSchedule() async {
        let h = harness(cookies: [router(endingIn: 600)], page: alive)
        h.silent.hold = true
        let look = Task { await h.model.tendSession() }
        await waitUntil { h.silent.attempts == 1 }
        h.model.automaticSignIn = false
        XCTAssertEqual(h.tasks.cancelled, 1)
        h.silent.release()
        await look.value
        XCTAssertTrue(h.vault.saves.isEmpty)
        XCTAssertTrue(h.tasks.submitted.isEmpty)
    }

    @MainActor
    func testSwitchingTheSettingOnAgainMayTryRightAway() async {
        let h = harness(cookies: [router(endingIn: 600)], page: alive)
        h.silent.result = SilentResult(outcome: .timedOut)
        await h.model.tendSession()
        h.model.automaticSignIn = false
        h.model.automaticSignIn = true
        await h.model.tendSession()
        XCTAssertEqual(h.silent.attempts, 2)
    }

    @MainActor
    func testAVaultThatCannotSaveIsAFailure() async {
        let h = harness(cookies: [router(endingIn: 600)], page: alive)
        h.vault.failure = SyncFailure(message: "Keychain error")
        await h.model.tendSession()
        XCTAssertNotNil(h.model.care.failedAt)
        XCTAssertFalse(h.model.sessionNoteVisible)
    }

    @MainActor
    func testAnExpiredPageSignsInAgainBeforeAskingTheStudent() async throws {
        let h = harness(cookies: [cookie("JSESSIONID")], page: alive)
        let http = FakeBlackboardHTTP()
        http.set(announcementsPath, .failure(.loginRequired))
        h.model.connectFeatures(http: http, tenant: tenant)
        h.model.saveSession = { _, _ in http.set(announcementsPath, json: #"{"results": []}"#) }
        let announcements = try XCTUnwrap(h.model.features).announcements
        await announcements.refresh()
        await waitUntil { announcements.phase == .loaded }
        XCTAssertEqual(h.silent.attempts, 1)
        XCTAssertFalse(h.model.needsSignIn)
        XCTAssertTrue(h.model.hasSession)
    }

    @MainActor
    func testAPageStillRefusedAfterASignInThatWorkedDoesNotLoop() async throws {
        let h = harness(cookies: [cookie("JSESSIONID")], page: alive)
        let http = FakeBlackboardHTTP()
        http.set(announcementsPath, .failure(.loginRequired))
        h.model.connectFeatures(http: http, tenant: tenant)
        let announcements = try XCTUnwrap(h.model.features).announcements
        await announcements.refresh()
        await waitUntil { h.model.needsSignIn }
        XCTAssertEqual(h.silent.attempts, 1)
    }

    @MainActor
    func testAnExpiredPageShowsReconnectWhenTheSchoolWantsTheStudent() async throws {
        let h = harness(cookies: [cookie("JSESSIONID")], page: alive)
        h.silent.result = SilentResult(outcome: .needsInteraction)
        let http = FakeBlackboardHTTP()
        http.set(announcementsPath, .failure(.loginRequired))
        h.model.connectFeatures(http: http, tenant: tenant)
        let announcements = try XCTUnwrap(h.model.features).announcements
        await announcements.refresh()
        await waitUntil { h.model.needsSignIn }
    }

    /// The app's library, for the work that needs it: checking the account and finding courses.
    @MainActor
    private func started(_ h: Harness, page: @escaping (String) async throws -> [String: Any]) async {
        await h.model.start(restoreSession: false)
        h.model.install(tenant: tenant, cookies: [cookie("JSESSIONID")], pageLoader: page)
    }

    @MainActor
    func testWorkThatFindsTheSessionOverSignsInAgainAndGoesOn() async {
        let h = harness(page: alive)
        var calls = 0
        let expired = self.expired, alive = self.alive
        await started(h) { path in
            calls += 1
            return try await (calls == 1 ? expired : alive)(path)
        }
        h.model.refreshCourses()
        await waitUntil { !h.model.busy }
        XCTAssertEqual(h.silent.attempts, 1)
        XCTAssertGreaterThan(calls, 2, "the check ran again and went on to the courses")
        XCTAssertFalse(h.model.needsSignIn)
        XCTAssertNil(h.model.errorMessage)
    }

    @MainActor
    func testWorkFallsBackToSignInWhenTheBackgroundSignInFails() async {
        let h = harness(page: alive)
        h.silent.result = SilentResult(outcome: .needsInteraction)
        await started(h, page: expired)
        h.model.refreshCourses()
        await waitUntil { !h.model.busy }
        XCTAssertEqual(h.silent.attempts, 1, "one try, not a loop")
        XCTAssertTrue(h.model.needsSignIn)
        XCTAssertEqual(h.model.status, "Sign-in needed")
    }

    @MainActor
    func testNoCoursesOnBlackboardSaysSoInTheStatus() async {
        let h = harness(page: alive)
        await started(h, page: alive)  // the account answers, and its course list is empty
        h.model.refreshCourses()
        await waitUntil { !h.model.busy }
        XCTAssertTrue(h.model.terms.isEmpty)
        XCTAssertEqual(h.model.status, AppModel.noCoursesFound)
        // Shown in the app's language from the shared string table.
        XCTAssertEqual(L10n.text(AppModel.noCoursesFound, language: "en"), AppModel.noCoursesFound)
        XCTAssertTrue(L10n.text(AppModel.noCoursesFound, language: "tr").hasPrefix("Blackboard'da ders bulunamadı"))
    }

    @MainActor
    func testASessionBackAfterReconnectWasShownEndsTheReconnectState() async {
        let h = harness(page: alive)
        var over = true
        let expired = self.expired, alive = self.alive
        await started(h) { path in try await (over ? expired : alive)(path) }
        h.silent.result = SilentResult(outcome: .timedOut)
        await h.model.tendSession()
        XCTAssertTrue(h.model.needsSignIn)
        // Later, in the background, the sign-on worked again.
        over = false
        h.silent.result = SilentResult(outcome: .refreshed, cookies: [router(endingIn: 3600)])
        h.model.automaticSignIn = false
        h.model.automaticSignIn = true
        await h.model.backgroundRefresh()
        XCTAssertTrue(h.model.needsSignIn, "the screen waits for the next open")
        await h.model.tendSession()
        await waitUntil { !h.model.needsSignIn && !h.model.busy }
        XCTAssertTrue(h.model.hasSession)
    }

    @MainActor
    func testGoingToTheBackgroundAsksForTheNextLook() {
        let h = harness(cookies: [router(endingIn: 3600)], page: alive)
        h.model.enterBackground()
        XCTAssertEqual(h.tasks.submitted.count, 1)
        h.tasks.refuse = true // the simulator has no background refresh
        h.model.enterBackground()
        h.model.automaticSignIn = false
        h.model.enterBackground()
        XCTAssertGreaterThan(h.tasks.cancelled, 0)
    }

    @MainActor
    func testBackgroundRefreshHasItsShortBudgetAndAsksForTheNextOne() async {
        let h = harness(cookies: [router(endingIn: 600)], page: alive)
        await h.model.backgroundRefresh()
        XCTAssertEqual(h.silent.timeouts, [SessionCare.backgroundTimeout])
        XCTAssertEqual(h.vault.saves.count, 1)
        XCTAssertEqual(h.tasks.submitted.count, 1)
        XCTAssertNil(h.model.care.checkedAt, "the next open looks again")
    }

    @MainActor
    func testBackgroundRefreshLeavesTheScreenForTheNextOpen() async {
        let h = harness(cookies: [router(endingIn: -60)], page: expired)
        h.silent.result = SilentResult(outcome: .needsInteraction)
        await h.model.backgroundRefresh()
        XCTAssertFalse(h.model.needsSignIn)
        await h.model.tendSession()
        XCTAssertTrue(h.model.needsSignIn, "the open finds out: keep-alive, then the wait after the failure")
        XCTAssertEqual(h.silent.attempts, 1)
    }

    @MainActor
    func testBackgroundRefreshStartsFromTheVaultWhenTheAppWasNotRunning() async {
        let model = AppModel(), silent = FakeSilentSignIn(), tasks = FakeBackgroundTasks()
        model.silentSignIn = silent
        model.backgroundTasks = tasks
        model.saveSession = { _, _ in }
        model.loadSession = { nil }
        await model.backgroundRefresh()
        XCTAssertEqual(silent.attempts, 0)
        XCTAssertEqual(tasks.submitted.count, 0, "signed out: nothing to wake up for")
        XCTAssertEqual(tasks.cancelled, 1)
    }

    @MainActor
    func testTheSettingIsOnByDefault() {
        XCTAssertTrue(AppModel().automaticSignIn)
    }
}

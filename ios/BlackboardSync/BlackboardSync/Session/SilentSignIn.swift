import BackgroundTasks
import UIKit
import WebKit

// Signing in again without the student. A Blackboard session ends after about an hour, but the school's
// single sign-on usually outlives it. So a hidden web view on the sign-in browser's own data store opens
// Blackboard; the sign-on finds its cookies there and sends it straight back signed in.
//
// Nothing here ever types, reads or stores a password, and no form is touched. When the school wants the
// student, the attempt just ends and the app shows Sign in as it always did.

struct SilentResult {
    var outcome: SilentOutcome
    var cookies: [HTTPCookie] = []
}

@MainActor
protocol SilentSignIn {
    func attempt(tenant: URL, timeout: TimeInterval) async -> SilentResult
}

/// The page the attempt watches; a fake in the tests.
@MainActor
protocol SilentPage: AnyObject {
    /// Blackboard's old cookies go first: they may still work for a few minutes, and saving those again
    /// would refresh nothing. The sign-on's cookies stay.
    func open(_ tenant: URL) async
    func cookies() async -> [HTTPCookie]
    /// The page shows a password field. It is only looked at, never touched.
    func wantsStudent() -> Bool
    var host: String? { get }
    /// Set when the page cannot go on.
    var failure: SilentOutcome? { get }
    func close()
}

/// Whether Blackboard accepts these cookies: the app's own account check, with nothing saved.
@MainActor
func sessionAccepted(tenant: URL, cookies: [HTTPCookie], timeout: TimeInterval) async -> Bool {
    let api = BlackboardAPI(tenant: tenant, cookies: cookies, persistSession: false, requestTimeout: timeout, log: { _ in })
    defer { api.cancel() }
    return (try? await api.json(BlackboardAPI.accountPath, label: "Account"))?["id"] is String
}

@MainActor
final class BrowserSilentSignIn: SilentSignIn {
    private static let checkTimeout: TimeInterval = 10
    private let makePage: @MainActor () -> any SilentPage
    private let check: @MainActor (URL, [HTTPCookie], TimeInterval) async -> Bool
    private let now: () -> Date
    private let pause: () async -> Void

    init(page: @escaping @MainActor () -> any SilentPage,
         check: @escaping @MainActor (URL, [HTTPCookie], TimeInterval) async -> Bool = { await sessionAccepted(tenant: $0, cookies: $1, timeout: $2) },
         now: @escaping () -> Date = Date.init,
         pause: @escaping () async -> Void = { try? await Task.sleep(for: .seconds(1)) }) {
        makePage = page; self.check = check; self.now = now; self.pause = pause
    }

    convenience init(store: WKWebsiteDataStore) {
        self.init(page: { WebSilentPage(store: store) })
    }

    func attempt(tenant: URL, timeout: TimeInterval) async -> SilentResult {
        let page = makePage()
        defer { page.close() }
        await page.open(tenant)
        let deadline = now().addingTimeInterval(timeout)
        while now() < deadline {
            guard !Task.isCancelled else { return SilentResult(outcome: .cancelled) }
            let cookies = SessionCare.sessionCookies(await page.cookies(), tenant: tenant)
            let left = deadline.timeIntervalSince(now())
            if !cookies.isEmpty, left > 0, await check(tenant, cookies, min(left, Self.checkTimeout)) {
                return SilentResult(outcome: .refreshed, cookies: cookies)
            }
            guard !Task.isCancelled else { return SilentResult(outcome: .cancelled) }
            if page.wantsStudent() { return SilentResult(outcome: .needsInteraction) }
            if let failure = page.failure { return SilentResult(outcome: failure) }
            await pause()
        }
        // Still somewhere else after all this time: a page that asks for something other than a password.
        let away = page.host.map { $0.lowercased() != tenant.host?.lowercased() } ?? false
        return SilentResult(outcome: away ? .needsInteraction : .timedOut)
    }
}

/// A web view the student never sees or touches. No UI delegate, so popups and dialogs go nowhere.
@MainActor
final class WebSilentPage: NSObject, SilentPage, WKNavigationDelegate {
    private static let passwordField = """
        Array.from(document.querySelectorAll('input[type=password]')).some(function (field) {
            var box = field.getBoundingClientRect();
            return box.width > 0 && box.height > 0 && getComputedStyle(field).visibility !== 'hidden';
        })
        """
    private let store: WKWebsiteDataStore
    private var view: WKWebView?
    private var passwordShown = false
    private(set) var failure: SilentOutcome?

    init(store: WKWebsiteDataStore) { self.store = store }

    var host: String? { view?.url?.host }

    func open(_ tenant: URL) async {
        let cookieStore = store.httpCookieStore
        for cookie in SessionCare.blackboardOwned(await cookieStore.allCookies(), tenant: tenant) {
            await cookieStore.deleteCookie(cookie)
        }
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = store
        // A page's size, so that sign-on pages lay out and the password field can be seen.
        let view = WKWebView(frame: CGRect(x: 0, y: 0, width: 1024, height: 768), configuration: configuration)
        view.navigationDelegate = self
        view.isUserInteractionEnabled = false
        view.accessibilityElementsHidden = true
        view.alpha = 0
        // In the window, behind everything: WebKit throttles a page that is in none. In the background there is none.
        keyWindow?.insertSubview(view, at: 0)
        self.view = view
        view.load(URLRequest(url: tenant))
    }

    func cookies() async -> [HTTPCookie] { await store.httpCookieStore.allCookies() }

    /// Answers from the look before: a suspended page never replies, and that must not stop the deadline.
    func wantsStudent() -> Bool {
        view?.evaluateJavaScript(Self.passwordField) { [weak self] result, _ in
            if result as? Bool == true { self?.passwordShown = true }
        }
        return passwordShown
    }

    func close() {
        view?.stopLoading()
        view?.navigationDelegate = nil
        view?.removeFromSuperview()
        view = nil
    }

    private var keyWindow: UIWindow? {
        UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }
            .flatMap(\.windows).first(where: \.isKeyWindow)
    }

    private func navigationFailed(_ error: Error) {
        let error = error as NSError
        // A redirect that replaces the running load reports "cancelled"; the next page decides.
        if error.domain == NSURLErrorDomain, error.code != NSURLErrorCancelled { failure = .unreachable }
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        navigationFailed(error)
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        navigationFailed(error)
    }

    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) { failure = .webFailed }
}

/// The background refresh requests; a fake in the tests.
protocol BackgroundScheduling {
    func submit(earliest: Date) throws
    func cancel()
}

struct SystemBackgroundTasks: BackgroundScheduling {
    func submit(earliest: Date) throws {
        let request = BGAppRefreshTaskRequest(identifier: SessionCare.backgroundTaskID)
        request.earliestBeginDate = earliest
        try BGTaskScheduler.shared.submit(request)
    }

    func cancel() { BGTaskScheduler.shared.cancel(taskRequestWithIdentifier: SessionCare.backgroundTaskID) }
}

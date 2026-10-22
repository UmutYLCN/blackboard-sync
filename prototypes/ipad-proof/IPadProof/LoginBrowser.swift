import SwiftUI
import WebKit

struct LoginBrowser: UIViewRepresentable {
    let webView: WKWebView
    let origin: (String) -> Void
    let event: (String) -> Void

    func makeCoordinator() -> Coordinator { Coordinator(origin: origin, event: event) }
    func makeUIView(context: Context) -> WKWebView {
        webView.navigationDelegate = context.coordinator
        webView.uiDelegate = context.coordinator
        return webView
    }
    func updateUIView(_ uiView: WKWebView, context: Context) {}

    final class Coordinator: NSObject, WKNavigationDelegate, WKUIDelegate {
        let origin: (String) -> Void
        let event: (String) -> Void
        init(origin: @escaping (String) -> Void, event: @escaping (String) -> Void) {
            self.origin = origin; self.event = event
        }

        func webView(_ webView: WKWebView, didCommit navigation: WKNavigation!) {
            guard let url = webView.url else { return }
            // Show the page origin; omit credentials, SSO paths, fragments, and query parameters.
            origin((url.scheme ?? "") + "://" + (url.host ?? "") + (url.port.map { ":\($0)" } ?? ""))
        }

        func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
            event("Sign-in navigation: " + ProofLogic.safeError(error))
        }
        func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
            event("Sign-in navigation: " + ProofLogic.safeError(error))
        }
        func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
            event("Sign-in web process terminated. Close and reopen Sign in to retry.")
        }
        func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                     for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
            // Keep target=_blank / window.open sign-in navigation visible in the owned web view.
            if navigationAction.targetFrame == nil { webView.load(navigationAction.request) }
            return nil
        }
    }
}

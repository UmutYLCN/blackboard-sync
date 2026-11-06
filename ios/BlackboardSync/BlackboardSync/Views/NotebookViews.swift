import SwiftUI
import UIKit

/// Home's NotebookLM card, under the status card as on the Mac: how many courses have new files.
struct NotebookCard: View {
    @EnvironmentObject var model: AppModel
    var body: some View {
        let count = model.notebookCourses.filter { !$0.newFiles.isEmpty }.count
        Card {
            HStack(alignment: .top, spacing: 14) {
                Image(systemName: count > 0 ? "text.book.closed.fill" : "text.book.closed")
                    .font(.system(size: 26)).foregroundStyle(count > 0 ? Color.appAccent : Color.secondary).frame(width: 32)
                VStack(alignment: .leading, spacing: 6) {
                    Text("NotebookLM").font(.title3.weight(.light))
                    Text(detail(count)).font(.callout).foregroundStyle(.secondary)
                }
                Spacer(minLength: 8)
                ViewAllButton(page: .notebooklm, title: "Open").accessibilityIdentifier("notebook.open")
            }
        }
    }
    private func detail(_ count: Int) -> String {
        if count == 0 { return model.text("No new files to send.") }
        let key = count == 1 ? "{n} course has new files." : "{n} courses have new files."
        return model.text(key).replacingOccurrences(of: "{n}", with: String(count))
    }
}

/// The courses with new files, each with one Send button that hands them to the system share sheet.
/// The student picks NotebookLM and the course's notebook there; the app cannot choose either.
struct NotebookSendPage: View {
    @EnvironmentObject var model: AppModel
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                Text(model.text("Tap Send, choose NotebookLM, then pick the course's notebook. You need the NotebookLM app on this iPad."))
                    .font(.callout).foregroundStyle(.secondary)
                if let error = model.notebookError {
                    Text(model.text(error)).font(.callout).foregroundStyle(.orange)
                }
                if model.notebookCourses.isEmpty {
                    Card {
                        Text(model.text("No course files to send yet.")).font(.headline)
                        Text(model.text("Select your courses and tap Sync now.")).font(.callout).foregroundStyle(.secondary)
                    }
                }
                ForEach(model.notebookCourses) { NotebookCourseRow(course: $0) }
            }.padding(24).frame(maxWidth: 800)
                .frame(maxWidth: .infinity)
        }.background(Color(uiColor: .systemGroupedBackground))
            .navigationTitle(model.text("Send to NotebookLM"))
            .task { await model.refreshNotebook() }
    }
}

private struct NotebookCourseRow: View {
    @EnvironmentObject var model: AppModel
    let course: NotebookCourse
    @State private var sheet = NotebookShareSheet()
    var body: some View {
        Card {
            HStack(spacing: 14) {
                VStack(alignment: .leading, spacing: 6) {
                    Text(course.title).font(.headline).lineLimit(2)
                    if !course.newFiles.isEmpty { Text(detail).font(.callout).foregroundStyle(.secondary) }
                }
                Spacer(minLength: 8)
                if course.newFiles.isEmpty {
                    Label(model.text("All sent"), systemImage: "checkmark.circle.fill")
                        .font(.subheadline.weight(.semibold)).foregroundStyle(.green)
                } else {
                    Button(model.text("Send"), action: send).buttonStyle(.pill)
                        .background(ShareAnchor(sheet: sheet))
                        .accessibilityLabel(Text(model.text("Send") + ": " + course.title))
                        .accessibilityIdentifier("notebook.send")
                }
            }
        }
    }
    private var detail: String {
        let count = course.newFiles.count
        return model.text(count == 1 ? "{n} new file" : "{n} new files").replacingOccurrences(of: "{n}", with: String(count))
    }
    private func send() {
        Task {
            // Look again first: a file may have been deleted in Files since the page was drawn.
            guard let current = await model.notebookCourseToSend(course.id) else { return }
            let shown = sheet.present(current.newFiles.map(\.url)) { activity, completed, error in
                Task { await model.notebookShareFinished(current, activity: activity, completed: completed, error: error) }
            }
            if !shown { model.notebookError = "Could not open the share sheet. Try again." }
        }
    }
}

/// UIActivityViewController, not ShareLink: only it reports whether the share completed. It is
/// presented from the Send button because on iPad it is a popover and needs one to point at.
@MainActor
final class NotebookShareSheet {
    weak var anchor: UIView?
    /// Weak, so it clears itself however the sheet went away. The sheet may call back more than once:
    /// an extension that is cancelled reports that, and the sheet can stay open to pick another app.
    private weak var active: UIActivityViewController?

    func present(_ urls: [URL], finished: @escaping (_ activity: String?, _ completed: Bool, _ error: Error?) -> Void) -> Bool {
        guard active == nil, let anchor, var top = anchor.window?.rootViewController else { return false }
        while let next = top.presentedViewController { top = next }
        let controller = UIActivityViewController(activityItems: urls, applicationActivities: nil)
        controller.popoverPresentationController?.sourceView = anchor
        controller.popoverPresentationController?.sourceRect = anchor.bounds
        controller.completionWithItemsHandler = { activity, completed, _, error in
            finished(activity?.rawValue, completed, error)
        }
        active = controller
        top.present(controller, animated: true)
        return true
    }
}

private struct ShareAnchor: UIViewRepresentable {
    let sheet: NotebookShareSheet
    func makeUIView(context: Context) -> UIView {
        let view = UIView()
        view.isUserInteractionEnabled = false
        return view
    }
    func updateUIView(_ view: UIView, context: Context) { sheet.anchor = view }
}

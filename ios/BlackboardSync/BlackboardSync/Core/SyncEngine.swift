import Foundation

enum TransferResult {
    static let sizeCap: Int64 = 500_000_000
    case unchanged
    case skipped(String)
    case file(URL, etag: String?, lastModified: String?)
}

@MainActor
protocol MirrorAPI: AnyObject {
    func contents(courseID: String, parentID: String?) async throws -> [ContentItem]
    func fetch(path: String, name: String, previous: FileRecord?) async throws -> TransferResult
}

struct PlannedFile {
    var key: String
    var name: String
    var desired: String
    var requestPath: String // In-memory only: may contain a short-lived signed URL.
    var fingerprint: String?
    var mime: String?
}

struct SyncProgress {
    var discovered = 0
    var completed = 0
    var downloaded = 0
    var unchanged = 0
    var skipped = 0
    var failed = 0
    var currentName = ""
    var discovering = true
}

/// Fresh discovery on retry/relaunch avoids persisting expiring URLs. Each completed file is
/// checkpointed; a bounded sliding window limits live transfers to three.
@MainActor
final class SyncEngine {
    private let api: MirrorAPI
    private let store: LibraryStore
    private let scope: String
    private var progress = SyncProgress()
    private let update: (SyncProgress) -> Void
    init(api: MirrorAPI, store: LibraryStore, scope: String, update: @escaping (SyncProgress) -> Void) {
        self.api = api; self.store = store; self.scope = scope; self.update = update
    }

    func run(terms: [Term], selected: Set<String>) async throws -> SyncProgress {
        try await store.begin()
        do {
            var plan: [PlannedFile] = []
            for term in terms {
                for course in term.courses where selected.contains(course.id) {
                    try Task.checkCancellation()
                    let folder = try await store.courseFolder(course, term: term, scope: scope)
                    var visited: Set<String> = []
                    try await discover(course: course, parent: nil, folder: folder, depth: 0, visited: &visited, plan: &plan)
                }
            }
            progress.discovering = false
            progress.discovered = plan.count
            update(progress)
            try await withThrowingTaskGroup(of: Activity.self) { group in
                var next = 0
                func enqueue() {
                    guard next < plan.count else { return }
                    let file = plan[next]; next += 1
                    group.addTask { @MainActor in try await self.sync(file) }
                }
                for _ in 0..<min(3, plan.count) { enqueue() }
                while let activity = try await group.next() {
                    try Task.checkCancellation()
                    try await store.activity(activity)
                    progress.completed += 1; progress.currentName = activity.name
                    switch activity.status {
                    case .downloaded, .conflict: progress.downloaded += 1
                    case .unchanged: progress.unchanged += 1
                    case .skipped: progress.skipped += 1
                    case .failed: progress.failed += 1
                    default: break
                    }
                    update(progress)
                    enqueue()
                }
            }
            try await store.finish(success: progress.failed == 0)
            return progress
        } catch {
            try await store.finish(success: false)
            throw error
        }
    }

    private func discover(course: Course, parent: String?, folder: String, depth: Int,
                          visited: inout Set<String>, plan: inout [PlannedFile]) async throws {
        try Task.checkCancellation()
        guard depth <= 40, visited.count < 10_000 else { throw SyncFailure(message: "Course exceeds the folder safety limit.") }
        let items: [ContentItem]
        do { items = try await api.contents(courseID: course.id, parentID: parent) }
        catch {
            if Task.isCancelled || (error as? SyncFailure)?.authRequired == true { throw error }
            try await discoveryFailure(course.id + ":" + (parent ?? "root"), name: course.name, error: error)
            return
        }
        var folderNames: Set<String> = []
        for item in items {
            guard visited.insert(item.id).inserted else { continue }
            let itemKey = scope + ":" + course.id + ":" + item.id
            if let note = item.note, note != "No attachments for this content type." {
                try await discoveryFailure(itemKey, name: item.title, error: SyncFailure(message: note))
            }
            for attachment in item.attachments {
                let key = itemKey + ":attachment:" + attachment.id
                plan.append(PlannedFile(key: key, name: attachment.name,
                    desired: folder + "/" + MirrorPaths.name(attachment.name),
                    requestPath: "/learn/api/public/v1/courses/\(BlackboardAPI.segment(course.id))/contents/\(BlackboardAPI.segment(item.id))/attachments/\(BlackboardAPI.segment(attachment.id))/download",
                    fingerprint: item.modified.map { MirrorPaths.digest($0 + ":" + attachment.id + ":" + attachment.name) }))
            }
            for file in item.embedded {
                plan.append(PlannedFile(key: itemKey + ":xid:" + file.id, name: file.name,
                    desired: folder + "/" + MirrorPaths.name(file.name), requestPath: file.path,
                    fingerprint: item.modified.map { MirrorPaths.digest($0 + ":" + file.id + ":" + file.name) }, mime: file.mime))
            }
            if item.isFolder {
                var name = MirrorPaths.name(item.title)
                if !folderNames.insert(name.lowercased()).inserted { name = MirrorPaths.name(name + " (" + item.id + ")") }
                try await discover(course: course, parent: item.id, folder: folder + "/" + name,
                                   depth: depth + 1, visited: &visited, plan: &plan)
            }
            progress.discovered = plan.count; progress.currentName = item.title; update(progress)
        }
    }

    private func discoveryFailure(_ key: String, name: String, error: Error) async throws {
        progress.failed += 1
        try await store.activity(Activity(id: key, name: name, status: .failed, error: SyncLogic.safeError(error)))
        update(progress)
    }

    private func sync(_ file: PlannedFile) async throws -> Activity {
        try Task.checkCancellation()
        do {
            if MirrorPaths.isMedia(file.name, mime: file.mime) {
                return Activity(id: file.key, name: file.name, status: .skipped, error: "Audio and video are skipped.")
            }
            if try await store.unchanged(key: file.key, fingerprint: file.fingerprint) {
                let previous = await store.record(file.key)
                return Activity(id: file.key, name: file.name, relativePath: previous?.relativePath, status: .unchanged)
            }
            let record = await store.record(file.key)
            let previous: FileRecord?
            if let record, try await store.exists(record) { previous = record } else { previous = nil }
            let result = try await api.fetch(path: file.requestPath, name: file.name, previous: previous)
            switch result {
            case .unchanged:
                guard let previous, try await store.exists(previous) else { throw SyncFailure(message: "Local file is missing. Retry sync.") }
                return Activity(id: file.key, name: file.name, relativePath: previous.relativePath, status: .unchanged)
            case .skipped(let reason): return Activity(id: file.key, name: file.name, status: .skipped, error: reason)
            case .file(let temporary, let etag, let lastModified):
                defer { try? FileManager.default.removeItem(at: temporary) }
                try Task.checkCancellation()
                return try await store.install(key: file.key, desired: file.desired, temporary: temporary,
                                               fingerprint: file.fingerprint, etag: etag, lastModified: lastModified)
            }
        } catch {
            if Task.isCancelled || (error as? SyncFailure)?.authRequired == true { throw error }
            return Activity(id: file.key, name: file.name, status: .failed, error: SyncLogic.safeError(error))
        }
    }
}

import Foundation
import CryptoKit

struct FileRecord: Codable, Equatable {
    var relativePath: String
    var hash: String
    var fingerprint: String?
    var etag: String?
    var lastModified: String?
    var updated: Date
    var size: Int64
}

enum FileStatus: String, Codable { case pending, downloaded, unchanged, conflict, skipped, failed, cancelled }
struct Activity: Codable, Identifiable {
    var id: String
    var name: String
    var relativePath: String?
    var status: FileStatus
    var error: String?
    var date = Date()
}

struct LibraryState: Codable {
    var version = 1
    var records: [String: FileRecord] = [:]
    var folders: [String: String] = [:]
    var selected: [String: Set<String>] = [:]
    var terms: [Term] = []
    var activities: [Activity] = []
    var lastSync: Date?
    var interrupted = false
}

/// All manifest and local-file operations serialize on this actor, including conflict decisions.
/// Metadata stays in Application Support; Documents contains ordinary course files only.
actor LibraryStore {
    let documents: URL
    let stateURL: URL
    private var state: LibraryState
    private let fm = FileManager.default

    init(documents: URL, support: URL) throws {
        self.documents = documents
        stateURL = support.appendingPathComponent("library-v1.json")
        try FileManager.default.createDirectory(at: support, withIntermediateDirectories: true)
        if FileManager.default.fileExists(atPath: stateURL.path) {
            state = try JSONDecoder().decode(LibraryState.self, from: Data(contentsOf: stateURL))
        } else { state = LibraryState() }
        // An interrupted queue is discoverable/retryable after relaunch; completed records survive.
        if state.interrupted {
            for i in state.activities.indices where state.activities[i].status == .pending {
                state.activities[i].status = .cancelled
            }
        }
    }

    func snapshot() -> LibraryState { state }
    private func save() throws {
        try JSONEncoder().encode(state).write(to: stateURL, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
    }
    func setTerms(_ terms: [Term]) throws { state.terms = terms; try save() }
    func select(_ ids: Set<String>, scope: String) throws { state.selected[scope] = ids; try save() }

    func courseFolder(_ course: Course, term: Term, scope: String) throws -> String {
        let termKey = scope + ":term:" + term.id
        let termFolder: String
        if let existing = state.folders[termKey] { termFolder = existing }
        else {
            termFolder = try allocateFolder(key: termKey, desired: MirrorPaths.name(term.name))
        }
        let key = scope + ":course:" + course.id
        if let existing = state.folders[key] { return existing }
        return try allocateFolder(key: key, desired: termFolder + "/" + MirrorPaths.course(course))
    }

    private func allocateFolder(key: String, desired: String) throws -> String {
        var relative = desired
        var n = 2
        let taken = Set(state.folders.values.map { $0.folding(options: [.caseInsensitive, .diacriticInsensitive], locale: Locale(identifier: "en")) })
        while try taken.contains(relative.folding(options: [.caseInsensitive, .diacriticInsensitive], locale: Locale(identifier: "en"))) || fm.fileExists(atPath: url(relative).path) {
            relative = MirrorPaths.numbered(desired, n); n += 1
        }
        try fm.createDirectory(at: try url(relative), withIntermediateDirectories: true)
        state.folders[key] = relative
        try save()
        return relative
    }

    func folder(courseID: String, scope: String) -> String? { state.folders[scope + ":course:" + courseID] }

    /// Reject symlinks, traversal and noncanonical components, including edits through Files.
    func url(_ relative: String) throws -> URL {
        let parts = relative.split(separator: "/", omittingEmptySubsequences: false)
        guard !parts.isEmpty, parts.allSatisfy({ !$0.isEmpty && $0 != "." && $0 != ".." }) else {
            throw SyncFailure(message: "Unsafe local path rejected.")
        }
        let root = documents.appendingPathComponent("University", isDirectory: true)
        let result = root.appendingPathComponent(relative)
        let resolvedRoot = root.standardizedFileURL.path
        guard result.resolvingSymlinksInPath().path.hasPrefix(resolvedRoot + "/"),
              root.resolvingSymlinksInPath().path == resolvedRoot else {
            throw SyncFailure(message: "Unsafe local path rejected.")
        }
        // Refuse even an in-root symlink: external editors must not redirect writes.
        var cursor = root
        for part in parts {
            cursor.appendPathComponent(String(part))
            if (try? cursor.resourceValues(forKeys: [.isSymbolicLinkKey]).isSymbolicLink) == true {
                throw SyncFailure(message: "Unsafe local path rejected.")
            }
        }
        return result
    }

    static func hash(_ url: URL) throws -> String {
        let handle = try FileHandle(forReadingFrom: url)
        defer { try? handle.close() }
        var digest = SHA256()
        while let block = try handle.read(upToCount: 256 * 1024), !block.isEmpty { digest.update(data: block) }
        return digest.finalize().map { String(format: "%02x", $0) }.joined()
    }

    func record(_ key: String) -> FileRecord? { state.records[key] }
    func exists(_ record: FileRecord) throws -> Bool { fm.fileExists(atPath: try url(record.relativePath).path) }

    func unchanged(key: String, fingerprint: String?) throws -> Bool {
        guard let record = state.records[key], let fingerprint, record.fingerprint == fingerprint,
              try exists(record) else { return false }
        // Readability/hash are checked even when remote metadata lets us avoid a request.
        _ = try Self.hash(try url(record.relativePath))
        return true
    }

    func begin() throws {
        state.interrupted = true
        state.activities = []
        try save()
    }
    func activity(_ activity: Activity) throws {
        state.activities.removeAll { $0.id == activity.id }
        state.activities.insert(activity, at: 0)
        state.activities = Array(state.activities.prefix(1000))
        try save()
    }
    func finish(success: Bool) throws {
        state.interrupted = false
        if success { state.lastSync = Date() }
        try save()
    }

    /// Remote bytes are staged privately and only committed after MIME, size and HTML checks.
    /// A locally changed file is never replaced. The new record follows the remote copy beside it.
    func install(key: String, desired: String, temporary: URL, fingerprint: String?,
                 etag: String?, lastModified: String?) throws -> Activity {
        let digest = try Self.hash(temporary)
        let size = (try temporary.resourceValues(forKeys: [.fileSizeKey]).fileSize).map(Int64.init) ?? 0
        let previous = state.records[key]
        if let previous, previous.hash == digest, try exists(previous) {
            // Identical remote bytes: leave local annotations exactly as they are.
            var updated = previous
            updated.fingerprint = fingerprint; updated.etag = etag; updated.lastModified = lastModified
            state.records[key] = updated
            try save()
            return Activity(id: key, name: (previous.relativePath as NSString).lastPathComponent, relativePath: previous.relativePath, status: .unchanged)
        }
        var relative = previous?.relativePath ?? desired
        var conflict = false
        var target = try url(relative)
        if fm.fileExists(atPath: target.path) {
            let localHash = try Self.hash(target)
            if previous == nil || localHash != previous!.hash {
                conflict = previous != nil
                var n = 2
                repeat { relative = MirrorPaths.numbered(previous?.relativePath ?? desired, n); n += 1; target = try url(relative) }
                while fm.fileExists(atPath: target.path) || state.records.values.contains(where: { $0.relativePath.lowercased() == relative.lowercased() })
            }
        }
        // Copy beside the destination, then atomically rename. Coordination respects open-in-place editors.
        try fm.createDirectory(at: target.deletingLastPathComponent(), withIntermediateDirectories: true)
        let staged = target.deletingLastPathComponent().appendingPathComponent(".bbsync-\(UUID().uuidString).partial")
        defer { try? fm.removeItem(at: staged) }
        try fm.copyItem(at: temporary, to: staged)
        var coordinationError: NSError?
        var writeError: Error?
        NSFileCoordinator().coordinate(writingItemAt: target, options: .forReplacing, error: &coordinationError) { destination in
            do {
                // Check again inside coordination: an editor may have saved during the network request.
                if fm.fileExists(atPath: destination.path) {
                    guard let previous, !conflict, try Self.hash(destination) == previous.hash else {
                        throw SyncFailure(message: "Local file changed during save. Retry to preserve both copies.")
                    }
                    _ = try fm.replaceItemAt(destination, withItemAt: staged)
                } else { try fm.moveItem(at: staged, to: destination) }
            } catch { writeError = error }
        }
        if let error = coordinationError ?? writeError as NSError? { throw error }
        state.records[key] = FileRecord(relativePath: relative, hash: digest, fingerprint: fingerprint,
                                        etag: etag, lastModified: lastModified, updated: Date(), size: size)
        try save()
        return Activity(id: key, name: target.lastPathComponent, relativePath: relative, status: conflict ? .conflict : .downloaded)
    }

    func files(in relative: String) throws -> [LocalEntry] {
        let folder = relative.isEmpty ? documents.appendingPathComponent("University", isDirectory: true) : try url(relative)
        guard folder.resolvingSymlinksInPath().path == folder.standardizedFileURL.path else { throw SyncFailure(message: "Unsafe local path rejected.") }
        guard fm.fileExists(atPath: folder.path) else { return [] }
        return try fm.contentsOfDirectory(at: folder, includingPropertiesForKeys: [.isDirectoryKey, .isSymbolicLinkKey], options: [.skipsHiddenFiles])
            .filter { (try? $0.resourceValues(forKeys: [.isSymbolicLinkKey]).isSymbolicLink) != true }
            .map { LocalEntry(url: $0, isDirectory: (try? $0.resourceValues(forKeys: [.isDirectoryKey]).isDirectory) == true) }
            .sorted { $0.isDirectory != $1.isDirectory ? $0.isDirectory : $0.url.lastPathComponent.localizedStandardCompare($1.url.lastPathComponent) == .orderedAscending }
    }
}

struct LocalEntry: Identifiable {
    var id: String { url.path }
    let url: URL
    let isDirectory: Bool
}

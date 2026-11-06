import Foundation

/// A synced file ready to hand to NotebookLM. `hash` is the content the library recorded when the
/// file was listed, so a file that changes during a share is listed again afterwards.
struct NotebookFile: Equatable {
    let path: String
    let hash: String
    let url: URL
}

/// A course on the Send to NotebookLM page. `id` is the course's folder, unique per account and term.
struct NotebookCourse: Identifiable, Equatable {
    let id: String
    let title: String
    let newFiles: [NotebookFile]
}

/// A library file found on disk.
struct LocalFile: Equatable {
    let url: URL
    let size: Int64
}

/// What goes to NotebookLM from the iPad, following the Mac's rules (notebooklm/planner.py): the files
/// the sync recorded, never the student's own files in a course folder, in NotebookLM's formats.
/// Pure work: no network and no writes.
enum NotebookSend {
    static let supportedExtensions: Set<String> = ["pdf", "docx", "pptx", "txt", "md", "csv", "epub"]
    static let maxBytes: Int64 = 200 * 1024 * 1024 // NotebookLM's limit per source

    static func canSend(path: String, size: Int64) -> Bool {
        size > 0 && size <= maxBytes && supportedExtensions.contains((path as NSString).pathExtension.lowercased())
    }

    /// Each course folder's title, as its notebook is named on the Mac: the folder's name, with the
    /// term when two terms share that name.
    static func titles(_ folders: [String]) -> [String: String] {
        let name = { (folder: String) in (folder as NSString).lastPathComponent }
        let counts = Dictionary(folders.map { (name($0), 1) }, uniquingKeysWith: +)
        return Dictionary(folders.map { folder in
            let term = ((folder as NSString).deletingLastPathComponent as NSString).lastPathComponent
            return (folder, counts[name(folder)] == 1 ? name(folder) : name(folder) + " (" + term + ")")
        }, uniquingKeysWith: { first, _ in first })
    }

    /// The courses with something to send or already sent, in the order of `folders`. A course with
    /// no sendable files is left out. Identical content goes once: a file is new only when its hash
    /// was never sent for the course, and two copies of one file count as one.
    static func courses(folders: [String], records: [FileRecord], local: [String: LocalFile],
                        sent: [String: Set<String>]) -> [NotebookCourse] {
        let names = titles(folders)
        return folders.compactMap { folder in
            let sendable = records
                .filter { $0.relativePath.hasPrefix(folder + "/") }
                .compactMap { record -> NotebookFile? in
                    guard let file = local[record.relativePath],
                          canSend(path: record.relativePath, size: file.size) else { return nil }
                    return NotebookFile(path: record.relativePath, hash: record.hash, url: file.url)
                }
                .sorted { $0.path.localizedStandardCompare($1.path) == .orderedAscending }
            guard !sendable.isEmpty else { return nil }
            var seen = sent[folder] ?? []
            let new = sendable.filter { seen.insert($0.hash).inserted }
            return NotebookCourse(id: folder, title: names[folder] ?? folder, newFiles: new)
        }
    }
}

/// What has gone to NotebookLM from this iPad: each course folder's sent content hashes. It lives in
/// its own file beside the library's manifest, is never shared with the Mac, and survives re-sync:
/// a file downloaded again with the same content keeps its hash, and a changed file gets a new one.
struct NotebookLedger {
    private struct Contents: Codable {
        var version = 1
        var sent: [String: Set<String>] = [:]
    }

    let url: URL
    private(set) var sent: [String: Set<String>]

    init(support: URL) throws {
        url = support.appendingPathComponent("notebooklm-sent-v1.json")
        try FileManager.default.createDirectory(at: support, withIntermediateDirectories: true)
        if FileManager.default.fileExists(atPath: url.path) {
            sent = try JSONDecoder().decode(Contents.self, from: Data(contentsOf: url)).sent
        } else { sent = [:] }
    }

    /// Records a finished share of `course`'s listed files, and whether it counted. A cancelled or
    /// failed share leaves them listed, and so does one that ended at Apple's own Mail, Copy or Save
    /// to Files, which report completion too. The exception is Apple's wrapper for handing a file to
    /// another app, which is how NotebookLM would appear if it were not a share extension.
    mutating func shareFinished(_ course: NotebookCourse, activity: String?, completed: Bool, error: Error?) throws -> Bool {
        guard completed, error == nil else { return false }
        if let activity, activity.hasPrefix("com.apple."), !activity.contains("RemoteOpenInApplication") { return false }
        var updated = sent
        updated[course.id, default: []].formUnion(course.newFiles.map(\.hash))
        try JSONEncoder().encode(Contents(sent: updated))
            .write(to: url, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
        sent = updated
        return true
    }
}

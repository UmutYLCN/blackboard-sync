import Foundation

/// A Blackboard that answers from a table, for tests and SwiftUI previews. Paths are matched
/// exactly, query string included; anything unknown answers 404.
public final class FakeBlackboardHTTP: BlackboardHTTP, @unchecked Sendable {
    public enum Answer: Sendable {
        case json(Data)
        case failure(BlackboardHTTPError)
    }

    private let lock = NSLock()
    private var routes: [String: Answer]
    private var requested: [String] = []

    public init(_ routes: [String: Answer] = [:]) {
        self.routes = routes
    }

    public func set(_ path: String, _ answer: Answer) {
        lock.lock(); defer { lock.unlock() }
        routes[path] = answer
    }

    public func set(_ path: String, json: String) {
        set(path, .json(Data(json.utf8)))
    }

    /// Every path asked for, in order.
    public var calls: [String] {
        lock.lock(); defer { lock.unlock() }
        return requested
    }

    public func getJSON(_ path: String) async throws -> Data {
        let answer: Answer? = {
            lock.lock(); defer { lock.unlock() }
            requested.append(path)
            return routes[path]
        }()
        switch answer {
        case .json(let data): return data
        case .failure(let error): throw error
        case nil: throw BlackboardHTTPError.status(404)
        }
    }
}

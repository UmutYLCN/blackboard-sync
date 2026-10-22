import Foundation

/// The two REST roots the desktop client uses (`api.py`).
enum APIRoot {
    static let publicAPI = "/learn/api/public"
    static let privateAPI = "/learn/api/v1"
}

/// A paging link that would leave the tenant, or a loop of links.
public struct PagingError: Error, Equatable, Sendable {
    public let reason: String
}

enum Paging {
    /// The desktop has no limit; a cap keeps a server that links pages in a circle finite.
    static let maxPages = 100

    /// Every `results` element across `paging.nextPage` links (`BlackboardClient.get_paged`).
    /// All pages are read before anything is returned, so a failed later page fails the call
    /// and never yields a half list.
    static func all(_ path: String, query: String, http: BlackboardHTTP) async throws -> [JSONValue] {
        var next: String? = query.isEmpty ? path : "\(path)?\(query)"
        var visited: Set<String> = []
        var results: [JSONValue] = []
        while let current = next {
            guard isTenantPath(current) else { throw PagingError(reason: "paging link outside the tenant") }
            guard visited.insert(current).inserted, visited.count <= maxPages else {
                throw PagingError(reason: "paging does not end")
            }
            let page = try JSONValue.parse(try await http.getJSON(current))
            results += page["results"]?.array ?? []
            // nextPage already carries the query string.
            next = page["paging"]?["nextPage"]?.text
        }
        return results
    }

    /// A path on the same host: absolute, not protocol-relative, no scheme.
    static func isTenantPath(_ path: String) -> Bool {
        path.hasPrefix("/") && !path.hasPrefix("//") && !path.contains("://") && !path.contains("\\")
    }
}

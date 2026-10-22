import Foundation
import Security

// Cookie secrets live only in a device-only Keychain item, never in shared Documents/UserDefaults.
struct StoredCookie: Codable {
    let name: String
    let value: String
    let domain: String
    let path: String
    let secure: Bool
    let expires: Date?

    init(_ cookie: HTTPCookie) {
        name = cookie.name; value = cookie.value; domain = cookie.domain
        path = cookie.path; secure = cookie.isSecure; expires = cookie.expiresDate
    }

    var cookie: HTTPCookie? {
        var properties: [HTTPCookiePropertyKey: Any] = [
            .name: name, .value: value, .domain: domain, .path: path,
            .secure: secure ? "TRUE" : "FALSE"
        ]
        if let expires { properties[.expires] = expires }
        return HTTPCookie(properties: properties)
    }
}

struct SavedSession: Codable {
    let tenant: String
    let cookies: [StoredCookie]
}

enum SessionVault {
    private static var query: [String: Any] {
        [kSecClass as String: kSecClassGenericPassword,
         kSecAttrService as String: (Bundle.main.bundleIdentifier ?? "BlackboardSync") + ".session",
         kSecAttrAccount as String: "blackboard"]
    }

    static func load() throws -> SavedSession? {
        var request = query
        request[kSecReturnData as String] = true
        request[kSecMatchLimit as String] = kSecMatchLimitOne
        var result: CFTypeRef?
        let status = SecItemCopyMatching(request as CFDictionary, &result)
        if status == errSecItemNotFound { return nil }
        guard status == errSecSuccess, let data = result as? Data else {
            throw NSError(domain: NSOSStatusErrorDomain, code: Int(status))
        }
        return try JSONDecoder().decode(SavedSession.self, from: data)
    }

    static func save(tenant: URL, cookies: [HTTPCookie]) throws {
        let data = try JSONEncoder().encode(SavedSession(tenant: tenant.absoluteString,
                                                       cookies: cookies.map(StoredCookie.init)))
        let attributes: [String: Any] = [kSecValueData as String: data,
            kSecAttrAccessible as String: kSecAttrAccessibleWhenUnlockedThisDeviceOnly]
        let status = SecItemUpdate(query as CFDictionary, attributes as CFDictionary)
        if status == errSecItemNotFound {
            let added = SecItemAdd(query.merging(attributes) { _, new in new } as CFDictionary, nil)
            guard added == errSecSuccess else { throw NSError(domain: NSOSStatusErrorDomain, code: Int(added)) }
        } else if status != errSecSuccess {
            throw NSError(domain: NSOSStatusErrorDomain, code: Int(status))
        }
    }

    static func clear() throws {
        let status = SecItemDelete(query as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else {
            throw NSError(domain: NSOSStatusErrorDomain, code: Int(status))
        }
    }
}

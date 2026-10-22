import Foundation

/// Blackboard's JSON read loosely, the way the desktop reads it as dictionaries: a field of an
/// unexpected type is simply absent instead of failing the whole page.
public enum JSONValue: Decodable, Equatable, Sendable {
    case string(String)
    case number(Double)
    case bool(Bool)
    case array([JSONValue])
    case object([String: JSONValue])
    case null

    public init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let value = try? container.decode(Bool.self) {
            self = .bool(value)
        } else if let value = try? container.decode(Double.self) {
            self = .number(value)
        } else if let value = try? container.decode(String.self) {
            self = .string(value)
        } else if let value = try? container.decode([JSONValue].self) {
            self = .array(value)
        } else {
            self = .object(try container.decode([String: JSONValue].self))
        }
    }

    public static func parse(_ data: Data) throws -> JSONValue {
        do {
            return try JSONDecoder().decode(JSONValue.self, from: data)
        } catch {
            throw BlackboardHTTPError.notJSON
        }
    }

    public subscript(key: String) -> JSONValue? {
        if case .object(let object) = self { return object[key] }
        return nil
    }

    public var string: String? {
        if case .string(let value) = self { return value }
        return nil
    }

    /// A non-empty string, as Python's `x.get(key) or default` treats "" as missing.
    public var text: String? {
        guard let value = string, !value.isEmpty else { return nil }
        return value
    }

    public var number: Double? {
        if case .number(let value) = self { return value }
        return nil
    }

    public var bool: Bool? {
        if case .bool(let value) = self { return value }
        return nil
    }

    public var array: [JSONValue]? {
        if case .array(let value) = self { return value }
        return nil
    }

    /// Python truthiness, for `if item.get("draft")`.
    public var isTruthy: Bool {
        switch self {
        case .string(let value): return !value.isEmpty
        case .number(let value): return value != 0
        case .bool(let value): return value
        case .array(let value): return !value.isEmpty
        case .object(let value): return !value.isEmpty
        case .null: return false
        }
    }
}

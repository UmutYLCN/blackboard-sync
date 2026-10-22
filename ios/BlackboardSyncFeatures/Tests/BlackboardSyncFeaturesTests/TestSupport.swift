import Foundation
import XCTest
@testable import BlackboardSyncFeatures

let base = URL(string: "https://blackboard.example.edu")!
let cse = FeatureCourse(id: "_13004_1", name: "CSE303 Algorithm Analysis")
let mth = FeatureCourse(id: "_13010_1", name: "MTH201 Linear Algebra")
let istanbul = TimeZone(identifier: "Europe/Istanbul")!
let english = FeatureStrings(.english)
let turkish = FeatureStrings(.turkish)

func fixture(_ name: String) throws -> Data {
    let url = try XCTUnwrap(Bundle.module.url(forResource: name, withExtension: "json", subdirectory: "Fixtures"))
    return try Data(contentsOf: url)
}

func json(_ text: String) throws -> JSONValue {
    try JSONValue.parse(Data(text.utf8))
}

func utc(_ text: String) -> Date {
    ISODate.parse(text)!.date
}

/// A clock that tests can read from any thread.
final class Clock: @unchecked Sendable {
    private let lock = NSLock()
    private var value: Date

    init(_ value: Date) {
        self.value = value
    }

    var now: Date {
        get { lock.lock(); defer { lock.unlock() }; return value }
        set { lock.lock(); value = newValue; lock.unlock() }
    }
}

// swift-tools-version:5.10
import PackageDescription

// macOS is listed only so `swift test` runs on the Mac host; the app target is iPadOS 17.
let package = Package(
    name: "BlackboardSyncFeatures",
    defaultLocalization: "en",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [
        .library(name: "BlackboardSyncFeatures", targets: ["BlackboardSyncFeatures"]),
    ],
    targets: [
        .target(
            name: "BlackboardSyncFeatures",
            swiftSettings: [.enableExperimentalFeature("StrictConcurrency")]
        ),
        .testTarget(
            name: "BlackboardSyncFeaturesTests",
            dependencies: ["BlackboardSyncFeatures"],
            resources: [.copy("Fixtures")]
        ),
    ]
)

// swift-tools-version:5.9
import PackageDescription

// This Package.swift exists only so Xcode / SourceKit resolves the scaffold as
// a single module while the proper Pilot.xcodeproj is being set up (M0).
// Once Pilot.xcodeproj exists, this file can be deleted; the .app bundle
// requires an app target, which SwiftPM cannot produce on its own.

let package = Package(
    name: "Pilot",
    platforms: [.macOS(.v14)],
    products: [
        .executable(name: "Pilot", targets: ["Pilot"]),
    ],
    targets: [
        .executableTarget(
            name: "Pilot",
            path: "Pilot",
            exclude: ["Resources"]
        ),
    ]
)

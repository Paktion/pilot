import Foundation
import ApplicationServices
#if canImport(AppKit)
import AppKit
#endif

enum PermissionStatus {
    case granted, denied, notDetermined

    static func accessibility() -> PermissionStatus {
        AXIsProcessTrusted() ? .granted : .denied
    }

    static func screenRecording() -> PermissionStatus {
        #if canImport(AppKit)
        // CGPreflightScreenCaptureAccess is the canonical probe; wrap guarded
        // so the helper compiles in non-AppKit contexts (tests).
        return CGPreflightScreenCaptureAccess() ? .granted : .denied
        #else
        return .notDetermined
        #endif
    }
}

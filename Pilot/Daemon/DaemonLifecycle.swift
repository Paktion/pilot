import Foundation

enum DaemonLifecycle {
    static func resolvePython() -> String {
        for candidate in ["/opt/homebrew/bin/python3", "/usr/local/bin/python3", "/usr/bin/python3"] {
            if FileManager.default.isExecutableFile(atPath: candidate) {
                return candidate
            }
        }
        return "/usr/bin/env python3"
    }

    static func installLaunchAgent() throws {
        // Substitute {{PYTHON_PATH}} + {{PILOT_HOME}} into the template, write
        // to ~/Library/LaunchAgents/dev.pilot.daemon.plist, then launchctl
        // bootstrap gui/<uid>. Implementation: M0 onboarding.
        throw NSError(
            domain: "Pilot.DaemonLifecycle",
            code: 1,
            userInfo: [NSLocalizedDescriptionKey: "launch agent install not implemented (M0)"]
        )
    }
}

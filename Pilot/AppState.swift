import Foundation
import Combine

import Combine

@MainActor
final class AppState: ObservableObject {
    @Published var daemonConnected: Bool = false
    @Published var daemonVersion: String = ""
    @Published var activeRunID: String? = nil
    @Published var lastError: String? = nil
    @Published var dailyCost: Double = 0
    @Published var dailyBudget: Double = 5.0
    @Published var showOnboarding: Bool = false
    @Published var connectAttempting: Bool = false
    @Published var connectStatus: String = ""

    let client: DaemonClient
    private var costRefreshTask: Task<Void, Never>?
    private var cancellables: Set<AnyCancellable> = []

    init() {
        self.client = DaemonClient()
        // Mirror the client's live connection state into a @Published
        // property the UI can observe. Without this the dot is a liar.
        client.$isConnected
            .receive(on: RunLoop.main)
            .sink { [weak self] connected in
                self?.daemonConnected = connected
            }
            .store(in: &cancellables)
    }

    func startCostRefresh() {
        costRefreshTask?.cancel()
        costRefreshTask = Task { @MainActor [weak self] in
            guard let self else { return }
            while !Task.isCancelled {
                await self.refreshCost()
                try? await Task.sleep(nanoseconds: 10_000_000_000)  // 10s
            }
        }
    }

    /// Try to connect to the daemon. Reports progress via published status.
    func tryConnect() async {
        connectAttempting = true
        connectStatus = "connecting…"
        defer { connectAttempting = false }

        await client.connect()
        try? await Task.sleep(nanoseconds: 200_000_000)

        if client.isConnected {
            if let result = try? await client.callOnce(method: "health.check") {
                if let v = result["version"] as? String { self.daemonVersion = v }
                connectStatus = "connected"
            } else {
                connectStatus = "connected (no health reply)"
            }
        } else {
            connectStatus = daemonSocketExists()
                ? "socket found but handshake failed — try restarting the daemon"
                : "daemon not running — start it with: python -m pilot"
        }
    }

    /// Launch the Python daemon in a background Process. Returns true if the
    /// daemon became reachable. The launcher script path + its venv python
    /// are discovered in this order:
    ///   1. $PILOT_DAEMON_CMD (full command string in env)
    ///   2. ~/Library/Application Support/Pilot/launch.sh (bootstrapped once)
    ///   3. plain `python3 -m pilot` on PATH (assumes pip install -e)
    func startDaemon() async {
        connectAttempting = true
        connectStatus = "starting daemon…"
        defer { connectAttempting = false }

        if daemonSocketExists() {
            await tryConnect()
            return
        }

        let launcher = locateLauncher()
        let process = Process()
        process.launchPath = "/bin/zsh"
        process.arguments = ["-lc", launcher]
        process.standardOutput = FileHandle(forWritingAtPath: "/tmp/pilotd.out")
            ?? FileHandle.nullDevice
        process.standardError = process.standardOutput
        do {
            try process.run()
        } catch {
            connectStatus = "couldn't spawn daemon: \(error.localizedDescription)"
            return
        }

        // Poll until the socket appears, max ~8s.
        for _ in 0..<40 {
            try? await Task.sleep(nanoseconds: 200_000_000)
            if daemonSocketExists() {
                await tryConnect()
                return
            }
        }
        connectStatus = "daemon didn't start (see /tmp/pilotd.out)"
    }

    private func daemonSocketExists() -> Bool {
        let home = FileManager.default.homeDirectoryForCurrentUser
        let socket = home.appendingPathComponent("Library/Application Support/Pilot/pilotd.sock")
        // A Unix socket file shows up via fileExists; the socket itself isn't
        // a regular file but FileManager returns true for it on macOS.
        return FileManager.default.fileExists(atPath: socket.path)
    }

    private func locateLauncher() -> String {
        let env = ProcessInfo.processInfo.environment
        if let cmd = env["PILOT_DAEMON_CMD"], !cmd.isEmpty {
            return cmd
        }
        let home = FileManager.default.homeDirectoryForCurrentUser
        let shellScript = home.appendingPathComponent("Library/Application Support/Pilot/launch.sh").path
        if FileManager.default.isExecutableFile(atPath: shellScript) {
            return "'\(shellScript)'"
        }
        return "python3 -m pilot"
    }

    private func refreshCost() async {
        if !client.isConnected { await client.connect() }
        if let usage = try? await client.callOnce(method: "usage.summary") {
            self.dailyCost = usage["daily_cost"] as? Double ?? 0
            self.dailyBudget = usage["daily_budget"] as? Double ?? 5.0
        }
    }
}

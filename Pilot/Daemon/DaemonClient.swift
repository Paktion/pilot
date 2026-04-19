import Foundation
import Network

/// Blocking-style RPC client over the daemon's newline-delimited JSON protocol.
/// The Swift UI uses Network framework's NWConnection with a Unix endpoint.
/// Each public method is async and delivers events as they stream in.
@MainActor
final class DaemonClient: ObservableObject {
    @Published private(set) var isConnected: Bool = false
    @Published private(set) var lastError: String? = nil
    @Published private(set) var daemonVersion: String = ""

    private var connection: NWConnection?
    private let socketPath: URL
    private var pendingBuffer = Data()
    private var continuations: [UUID: AsyncThrowingStream<[String: Any], Error>.Continuation] = [:]
    private var requestIDToUUID: [String: UUID] = [:]

    init(socketPath: String? = nil) {
        if let override = socketPath {
            self.socketPath = URL(fileURLWithPath: override)
        } else {
            let home = FileManager.default.homeDirectoryForCurrentUser
            self.socketPath = home
                .appendingPathComponent("Library/Application Support/Pilot/pilotd.sock")
        }
    }

    // MARK: - Connection lifecycle

    func connect() async {
        // Tear down a stale non-ready connection before re-opening. Without
        // this, any prior .failed or .cancelled state leaves `connection`
        // non-nil and `connect()` becomes a silent no-op — which manifests
        // as "Library stuck on loading".
        if let existing = connection, existing.state != .ready {
            tearDownConnection(withError: "reconnecting")
        }
        guard connection == nil else { return }

        pendingBuffer.removeAll(keepingCapacity: true)
        let endpoint = NWEndpoint.unix(path: socketPath.path)
        let conn = NWConnection(to: endpoint, using: .tcp)
        conn.stateUpdateHandler = { [weak self] state in
            guard let self else { return }
            Task { @MainActor in
                switch state {
                case .ready:
                    self.isConnected = true
                case .failed(let error):
                    self.tearDownConnection(withError: error.localizedDescription)
                case .cancelled:
                    self.tearDownConnection(withError: nil)
                default:
                    break
                }
            }
        }
        self.connection = conn
        conn.start(queue: .main)
        receiveLoop()

        // Wait briefly for .ready.
        for _ in 0..<20 where !isConnected {
            try? await Task.sleep(nanoseconds: 50_000_000)
        }
    }

    func disconnect() {
        tearDownConnection(withError: nil)
    }

    private func tearDownConnection(withError message: String?) {
        if let conn = connection {
            conn.cancel()
        }
        connection = nil
        isConnected = false
        if let message { lastError = message }
        // Fail every pending continuation so callers don't hang forever.
        for (_, cont) in continuations {
            cont.finish(throwing: DaemonError.disconnected(message))
        }
        continuations.removeAll()
        requestIDToUUID.removeAll()
        pendingBuffer.removeAll(keepingCapacity: true)
    }

    // MARK: - RPC

    /// Send a one-shot request that expects a single ``done``/``error`` terminal event.
    /// Auto-reconnects once if the socket is stale.
    func callOnce(method: String, params: [String: Any] = [:]) async throws -> [String: Any] {
        // Reconnect-once retry: the daemon can restart between calls.
        for attempt in 0..<2 {
            do {
                if !isConnected { await connect() }
                let stream = try call(method: method, params: params)
                for try await frame in stream {
                    if let event = frame["event"] as? String,
                       event == "done" || event == "error" {
                        return frame
                    }
                }
                throw DaemonError.noTerminalEvent
            } catch {
                if attempt == 0 {
                    // Force a fresh connection on next iteration.
                    tearDownConnection(withError: "retry after: \(error)")
                    try? await Task.sleep(nanoseconds: 150_000_000)
                    continue
                }
                throw error
            }
        }
        throw DaemonError.noTerminalEvent
    }

    /// Stream every event frame tagged with the request's ``request_id``.
    func call(
        method: String,
        params: [String: Any] = [:]
    ) throws -> AsyncThrowingStream<[String: Any], Error> {
        guard let conn = connection else {
            throw DaemonError.notConnected
        }
        let requestID = UUID().uuidString
        let envelope: [String: Any] = [
            "request_id": requestID,
            "method": method,
            "params": params,
        ]
        var data = try JSONSerialization.data(withJSONObject: envelope)
        data.append(0x0A)  // newline framing

        let handle = UUID()
        var savedContinuation: AsyncThrowingStream<[String: Any], Error>.Continuation?
        let stream = AsyncThrowingStream<[String: Any], Error> { continuation in
            self.continuations[handle] = continuation
            self.requestIDToUUID[requestID] = handle
            savedContinuation = continuation
        }
        conn.send(content: data, completion: .contentProcessed { [weak self] err in
            guard let self else { return }
            if let err {
                Task { @MainActor in
                    self.continuations[handle]?.finish(throwing: err)
                    self.continuations[handle] = nil
                    self.requestIDToUUID.removeValue(forKey: requestID)
                }
            }
        })
        _ = savedContinuation  // capture suppressed-warning
        return stream
    }

    /// Convenience: cheap health.check call.
    @discardableResult
    func healthCheck() async -> [String: Any]? {
        do {
            if !isConnected { await connect() }
            let result = try await callOnce(method: "health.check")
            if let version = result["version"] as? String {
                self.daemonVersion = version
            }
            return result
        } catch {
            self.lastError = "\(error)"
            return nil
        }
    }

    // MARK: - Receive loop

    private func receiveLoop() {
        connection?.receive(minimumIncompleteLength: 1, maximumLength: 65_536) { [weak self] data, _, isComplete, err in
            guard let self else { return }
            if let data, !data.isEmpty {
                Task { @MainActor in
                    self.handleIncoming(data)
                }
            }
            if let err {
                Task { @MainActor in
                    self.lastError = err.localizedDescription
                }
                return
            }
            if !isComplete {
                Task { @MainActor in
                    self.receiveLoop()
                }
            }
        }
    }

    private func handleIncoming(_ data: Data) {
        pendingBuffer.append(data)
        while let newlineRange = pendingBuffer.firstRange(of: Data([0x0A])) {
            let lineData = pendingBuffer.subdata(in: 0..<newlineRange.lowerBound)
            pendingBuffer.removeSubrange(0..<newlineRange.upperBound)
            dispatchFrame(lineData)
        }
    }

    private func dispatchFrame(_ lineData: Data) {
        guard !lineData.isEmpty else { return }
        guard let frame = (try? JSONSerialization.jsonObject(with: lineData)) as? [String: Any] else {
            return
        }
        guard let reqID = frame["request_id"] as? String,
              let handle = requestIDToUUID[reqID] else {
            return
        }
        let continuation = continuations[handle]
        continuation?.yield(frame)
        if let event = frame["event"] as? String, event == "done" || event == "error" {
            continuation?.finish()
            continuations.removeValue(forKey: handle)
            requestIDToUUID.removeValue(forKey: reqID)
        }
    }
}

enum DaemonError: Error, LocalizedError {
    case notConnected
    case noTerminalEvent
    case disconnected(String?)

    var errorDescription: String? {
        switch self {
        case .notConnected: return "Daemon is not connected"
        case .noTerminalEvent: return "Daemon did not return a terminal event"
        case .disconnected(let msg): return "Daemon disconnected: \(msg ?? "unknown")"
        }
    }
}

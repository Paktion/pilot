import SwiftUI

/// Live event log for a running workflow. Subscribes to the stream returned by
/// ``workflow.run`` or ``workflow.subscribe`` and renders each frame as it
/// arrives.
struct RunConsoleView: View {
    let workflowName: String
    @EnvironmentObject var appState: AppState

    @State private var events: [LogEntry] = []
    @State private var isRunning: Bool = false
    @State private var finalStatus: String?
    @State private var finalSummary: String = ""
    @State private var runID: String?
    @State private var currentScreenshot: Data?
    @State private var startedAt: Date?

    var body: some View {
        HSplitView {
            eventsPane
                .frame(minWidth: 320, idealWidth: 460)

            screenshotPane
                .frame(minWidth: 280, idealWidth: 360)
        }
        .task(id: workflowName) { await runWorkflow() }
    }

    // MARK: - Subviews

    private var eventsPane: some View {
        VStack(alignment: .leading, spacing: 8) {
            header
            Divider()
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 4) {
                        ForEach(events) { entry in
                            LogRow(entry: entry).id(entry.id)
                        }
                    }
                    .padding(.horizontal, 8)
                }
                .onChange(of: events.count) { _, _ in
                    if let last = events.last?.id {
                        withAnimation { proxy.scrollTo(last, anchor: .bottom) }
                    }
                }
            }
            Divider()
            footer
        }
        .padding(12)
    }

    private var screenshotPane: some View {
        VStack(spacing: 8) {
            Text("Live view").font(.headline)
            if let data = currentScreenshot, let nsImage = NSImage(data: data) {
                Image(nsImage: nsImage)
                    .resizable()
                    .interpolation(.medium)
                    .aspectRatio(contentMode: .fit)
                    .frame(maxHeight: 520)
                    .background(.black)
                    .clipShape(RoundedRectangle(cornerRadius: 12))
                    .shadow(radius: 4)
            } else {
                RoundedRectangle(cornerRadius: 12)
                    .fill(.thinMaterial)
                    .overlay {
                        VStack(spacing: 6) {
                            Image(systemName: "iphone").font(.largeTitle)
                            Text("waiting for screenshot…")
                                .foregroundStyle(.secondary)
                                .font(.caption)
                        }
                    }
                    .frame(height: 520)
            }
            Spacer()
        }
        .padding(12)
    }

    private var header: some View {
        HStack {
            Circle().fill(statusColor).frame(width: 10, height: 10)
            VStack(alignment: .leading, spacing: 0) {
                Text(workflowName).font(.headline)
                if let rid = runID {
                    Text("run \(rid.prefix(8))")
                        .font(.caption2.monospaced())
                        .foregroundStyle(.secondary)
                }
            }
            Spacer()
            if isRunning {
                ProgressView().controlSize(.small)
            }
            Text(elapsedLabel).font(.caption.monospaced()).foregroundStyle(.secondary)
        }
    }

    private var footer: some View {
        HStack {
            if let s = finalStatus {
                Text("status: \(s)").font(.caption.monospaced())
                    .foregroundStyle(statusColor)
            }
            Spacer()
            if !finalSummary.isEmpty {
                Text(finalSummary).font(.caption).lineLimit(2)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private var statusColor: Color {
        switch finalStatus {
        case "success": return .green
        case "failed":  return .red
        case "aborted": return .yellow
        case "skipped": return .orange
        case nil:       return isRunning ? .blue : .gray
        default:        return .gray
        }
    }

    private var elapsedLabel: String {
        guard let t = startedAt else { return "—" }
        let s = Int(Date().timeIntervalSince(t))
        return String(format: "%02d:%02d", s / 60, s % 60)
    }

    // MARK: - Event loop

    private func runWorkflow() async {
        events = []
        finalStatus = nil
        finalSummary = ""
        isRunning = true
        startedAt = Date()
        defer { isRunning = false }

        if !appState.client.isConnected {
            await appState.client.connect()
        }
        do {
            let stream = try appState.client.call(
                method: "workflow.run",
                params: ["name": workflowName]
            )
            for try await frame in stream {
                handle(frame)
            }
        } catch {
            handle(["event": "error", "error": "\(error)"])
        }
    }

    private func handle(_ frame: [String: Any]) {
        let event = (frame["event"] as? String) ?? "?"
        switch event {
        case "started":
            runID = frame["run_id"] as? String
            events.append(.info("▶︎ started \(frame["workflow"] as? String ?? "")"))
        case "step":
            let idx = (frame["step"] as? Int) ?? 0
            let kind = (frame["kind"] as? String) ?? "?"
            events.append(.step("[\(idx)] \(kind)"))
        case "screenshot":
            if let b64 = frame["image_b64"] as? String,
               let data = Data(base64Encoded: b64) {
                currentScreenshot = data
            }
            if let meta = frame["meta"] as? [String: Any],
               let kind = meta["kind"] as? String {
                events.append(.screenshot("📸 \(kind)"))
            }
        case "chain":
            let child = frame["child_run_id"] as? String ?? "?"
            let status = frame["status"] as? String ?? "?"
            events.append(.info("→ chained \(child.prefix(8)) [\(status)]"))
        case "done":
            finalStatus = (frame["status"] as? String) ?? "done"
            finalSummary = (frame["summary"] as? String) ?? ""
            events.append(.done("✓ \(finalStatus ?? "") — \(finalSummary)"))
        case "failed", "aborted":
            finalStatus = event
            let msg = (frame["error"] as? String) ?? (frame["summary"] as? String) ?? ""
            events.append(.error("✗ \(event) — \(msg)"))
        case "error":
            finalStatus = "error"
            events.append(.error("✗ \(frame["error"] as? String ?? "unknown")"))
        default:
            events.append(.info("· \(event)"))
        }
    }
}

// MARK: - Model + row renderer

struct LogEntry: Identifiable {
    let id = UUID()
    let text: String
    let color: Color
    let font: Font
    let timestamp = Date()

    static func info(_ s: String) -> LogEntry {
        .init(text: s, color: .primary, font: .caption.monospaced())
    }
    static func step(_ s: String) -> LogEntry {
        .init(text: s, color: .blue, font: .caption.monospaced())
    }
    static func screenshot(_ s: String) -> LogEntry {
        .init(text: s, color: .teal, font: .caption.monospaced())
    }
    static func done(_ s: String) -> LogEntry {
        .init(text: s, color: .green, font: .caption.bold().monospaced())
    }
    static func error(_ s: String) -> LogEntry {
        .init(text: s, color: .red, font: .caption.bold().monospaced())
    }
}

struct LogRow: View {
    let entry: LogEntry
    private static let timeFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "HH:mm:ss"
        return f
    }()

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Text(Self.timeFormatter.string(from: entry.timestamp))
                .font(.caption2.monospaced())
                .foregroundStyle(.tertiary)
            Text(entry.text)
                .font(entry.font)
                .foregroundStyle(entry.color)
                .textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
    }
}

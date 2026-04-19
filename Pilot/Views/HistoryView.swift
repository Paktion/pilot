import SwiftUI

struct RunRow: Identifiable {
    let id: String
    let workflowID: String
    let status: String
    let startedAt: String
    let endedAt: String
    let cost: Double
    let summary: String

    init(raw: [String: Any]) {
        self.id = (raw["id"] as? String) ?? UUID().uuidString
        self.workflowID = (raw["workflow_id"] as? String) ?? "—"
        self.status = (raw["status"] as? String) ?? "—"
        self.startedAt = (raw["started_at"] as? String) ?? "—"
        self.endedAt = (raw["ended_at"] as? String) ?? ""
        self.cost = (raw["cost_usd"] as? Double) ?? 0
        self.summary = (raw["summary"] as? String) ?? ""
    }
}

struct HistoryView: View {
    @EnvironmentObject var appState: AppState
    @State private var runs: [RunRow] = []
    @State private var loadError: String?

    var body: some View {
        VStack(alignment: .leading) {
            HStack {
                Text("History").font(.title2).bold()
                Spacer()
                Button("Refresh") { Task { await reload() } }
            }
            if let loadError {
                Text(loadError).foregroundStyle(.red).font(.caption)
            } else if runs.isEmpty {
                Text("No runs recorded yet.").foregroundStyle(.secondary)
            } else {
                List(runs) { r in
                    HStack(alignment: .firstTextBaseline) {
                        Circle().fill(statusColor(r.status)).frame(width: 8, height: 8)
                        VStack(alignment: .leading) {
                            Text(r.summary.isEmpty ? r.workflowID : r.summary)
                                .lineLimit(1)
                            Text(r.startedAt.prefix(19))
                                .font(.caption.monospaced())
                                .foregroundStyle(.secondary)
                        }
                        Spacer()
                        Text(String(format: "$%.3f", r.cost))
                            .font(.caption.monospaced())
                            .foregroundStyle(.secondary)
                    }
                }
            }
            Spacer()
        }
        .padding()
        .task { await reload() }
    }

    private func statusColor(_ s: String) -> Color {
        switch s {
        case "success": return .green
        case "failed":  return .red
        case "aborted": return .yellow
        case "skipped": return .orange
        case "running": return .blue
        default:        return .gray
        }
    }

    private func reload() async {
        loadError = nil
        if !appState.client.isConnected {
            await appState.client.connect()
        }
        do {
            let result = try await appState.client.callOnce(method: "run.list", params: ["limit": 100])
            let raws = result["runs"] as? [[String: Any]] ?? []
            self.runs = raws.map(RunRow.init(raw:))
        } catch {
            self.loadError = "\(error)"
        }
    }
}

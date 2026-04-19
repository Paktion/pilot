import SwiftUI

struct LibraryView: View {
    @EnvironmentObject var appState: AppState
    @State private var workflows: [WorkflowSummary] = []
    @State private var loadError: String?
    @State private var isLoading: Bool = false
    @State private var runningWorkflowName: String?

    var body: some View {
        VStack(alignment: .leading) {
            HStack {
                Text("Library").font(.title2).bold()
                Spacer()
                Button { Task { await reload() } } label: {
                    Label("Refresh", systemImage: "arrow.clockwise")
                }
            }
            if isLoading {
                ProgressView("Loading workflows…")
            } else if let loadError {
                Text(loadError).foregroundStyle(.red).font(.caption)
            } else if workflows.isEmpty {
                Text("No workflows yet — use the Author tab to create one.")
                    .foregroundStyle(.secondary)
            } else {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 240))], spacing: 12) {
                    ForEach(workflows) { wf in
                        WorkflowCard(workflow: wf) { runningWorkflowName = wf.name }
                    }
                }
            }
            Spacer()
        }
        .padding()
        .task { await reload() }
        .sheet(item: Binding(
            get: { runningWorkflowName.map { RunSheet(id: $0) } },
            set: { runningWorkflowName = $0?.id }
        )) { sheet in
            VStack(spacing: 0) {
                HStack {
                    Text("Live run").font(.title3).bold()
                    Spacer()
                    Button("Close") { runningWorkflowName = nil }
                        .keyboardShortcut(.cancelAction)
                }
                .padding()
                Divider()
                RunConsoleView(workflowName: sheet.id)
                    .environmentObject(appState)
            }
            .frame(minWidth: 900, minHeight: 600)
        }
    }

    private func reload() async {
        isLoading = true
        loadError = nil
        defer { isLoading = false }
        if !appState.client.isConnected {
            await appState.client.connect()
        }
        do {
            let result = try await appState.client.callOnce(method: "workflow.list")
            let items = result["workflows"] as? [[String: Any]] ?? []
            self.workflows = items.compactMap(WorkflowSummary.init(raw:))
        } catch {
            self.loadError = "\(error)"
        }
    }
}

struct RunSheet: Identifiable, Hashable { let id: String }

struct WorkflowSummary: Identifiable, Hashable {
    let id: String
    let name: String
    let app: String
    let lastRunAt: String?
    let runCount: Int
    let successCount: Int

    init?(raw: [String: Any]) {
        guard let id = raw["id"] as? String, let name = raw["name"] as? String else {
            return nil
        }
        self.id = id
        self.name = name
        self.app = (raw["app"] as? String) ?? "—"
        self.lastRunAt = raw["last_run_at"] as? String
        self.runCount = (raw["run_count"] as? Int) ?? 0
        self.successCount = (raw["success_count"] as? Int) ?? 0
    }
}

struct WorkflowCard: View {
    let workflow: WorkflowSummary
    let runAction: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(workflow.name).font(.headline).lineLimit(2)
            Text(workflow.app).font(.caption).foregroundStyle(.secondary)
            HStack(spacing: 6) {
                if let last = workflow.lastRunAt, !last.isEmpty {
                    Text("last: \(last.prefix(16))").font(.caption2)
                } else {
                    Text("never run").font(.caption2).foregroundStyle(.secondary)
                }
                Spacer()
                Text("\(workflow.successCount)/\(workflow.runCount) ok")
                    .font(.caption2).foregroundStyle(.secondary)
            }
            Button("Run now", action: runAction).controlSize(.small)
        }
        .padding(12)
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 10))
    }
}

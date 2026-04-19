import SwiftUI

struct ScheduleJob: Identifiable {
    let id: String
    let name: String
    let nextRunTime: String
    let trigger: String

    init(raw: [String: Any]) {
        self.id = (raw["id"] as? String) ?? UUID().uuidString
        self.name = (raw["name"] as? String) ?? "—"
        self.nextRunTime = (raw["next_run_time"] as? String) ?? "—"
        self.trigger = (raw["trigger"] as? String) ?? "—"
    }
}

struct ScheduleView: View {
    @EnvironmentObject var appState: AppState
    @State private var jobs: [ScheduleJob] = []
    @State private var workflowName: String = ""
    @State private var cadenceText: String = ""
    @State private var parsedCron: String = ""
    @State private var status: String = ""

    var body: some View {
        VStack(alignment: .leading) {
            Text("Schedule").font(.title2).bold()
            HStack {
                Button("Refresh") { Task { await reload() } }
                Spacer()
            }
            GroupBox("New schedule") {
                VStack(alignment: .leading, spacing: 6) {
                    TextField("Workflow name", text: $workflowName)
                    HStack {
                        TextField("e.g. 'every Friday 5pm'", text: $cadenceText)
                        Button("Parse") { Task { await parseCadence() } }
                            .disabled(cadenceText.isEmpty)
                    }
                    HStack {
                        TextField("cron expression", text: $parsedCron)
                        Button("Create") { Task { await createJob() } }
                            .disabled(workflowName.isEmpty || parsedCron.isEmpty)
                    }
                    if !status.isEmpty {
                        Text(status).font(.caption).foregroundStyle(.secondary)
                    }
                }
                .padding(4)
            }
            if jobs.isEmpty {
                Text("No scheduled jobs.").foregroundStyle(.secondary).padding(.top)
            } else {
                List(jobs) { j in
                    HStack {
                        VStack(alignment: .leading) {
                            Text(j.name).font(.body)
                            Text(j.trigger).font(.caption.monospaced()).foregroundStyle(.secondary)
                        }
                        Spacer()
                        Text(j.nextRunTime.prefix(19))
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

    private func reload() async {
        if !appState.client.isConnected { await appState.client.connect() }
        do {
            let result = try await appState.client.callOnce(method: "schedule.list")
            let raws = result["jobs"] as? [[String: Any]] ?? []
            self.jobs = raws.map(ScheduleJob.init(raw:))
        } catch {
            self.status = "\(error)"
        }
    }

    private func parseCadence() async {
        do {
            let result = try await appState.client.callOnce(
                method: "schedule.parse_cadence",
                params: ["text": cadenceText]
            )
            if let cron = result["cron_expr"] as? String {
                self.parsedCron = cron
            } else if let err = result["error"] as? String {
                self.status = err
            }
        } catch {
            self.status = "\(error)"
        }
    }

    private func createJob() async {
        do {
            let result = try await appState.client.callOnce(
                method: "schedule.create",
                params: ["workflow_name": workflowName, "cron_expr": parsedCron]
            )
            if let jid = result["job_id"] as? String {
                self.status = "Created \(jid)"
                await reload()
            } else if let err = result["error"] as? String {
                self.status = err
            }
        } catch {
            self.status = "\(error)"
        }
    }
}

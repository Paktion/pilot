import SwiftUI

struct WorkflowDrawerView: View {
    @EnvironmentObject var appState: AppState
    let workflow: WorkflowEnriched
    let onClose: () -> Void

    @State private var tab: Tab = .overview

    enum Tab: String, CaseIterable, Identifiable {
        case overview, schedule, history, yaml
        var id: String { rawValue }
        var label: String {
            switch self {
            case .overview: return "Overview"
            case .schedule: return "Schedule"
            case .history: return "History"
            case .yaml: return "YAML"
            }
        }
    }

    var body: some View {
        HStack(spacing: 0) {
            Spacer(minLength: 0)
            VStack(alignment: .leading, spacing: 0) {
                header
                Rectangle().fill(PColor.line).frame(height: 0.5)
                tabsRow
                Rectangle().fill(PColor.line).frame(height: 0.5)
                ScrollView {
                    Group {
                        switch tab {
                        case .overview: DrawerOverview(wf: workflow)
                        case .schedule: DrawerSchedule(wf: workflow)
                        case .history: DrawerHistory(wf: workflow)
                        case .yaml: DrawerYaml(wf: workflow)
                        }
                    }
                    .padding(.horizontal, 20)
                    .padding(.vertical, 18)
                }
            }
            .frame(width: 520)
            .frame(maxHeight: .infinity)
            .background(PColor.bg1)
            .overlay(alignment: .leading) {
                Rectangle().fill(PColor.line).frame(width: 0.5)
            }
            .shadow(color: .black.opacity(0.4), radius: 50, x: -20)
        }
    }

    private var header: some View {
        HStack(spacing: PSpace.m) {
            AppMark(app: workflow.app, size: 36)
            VStack(alignment: .leading, spacing: 2) {
                Text(workflow.name)
                    .font(PFont.display(16, weight: .semibold))
                    .foregroundStyle(PColor.fg0)
                    .lineLimit(1)
                Text(workflow.app)
                    .font(PFont.ui(12))
                    .foregroundStyle(PColor.fg2)
            }
            Spacer(minLength: PSpace.s)
            PButton("Run now", icon: "play.fill",
                    variant: .primary, size: .small) {
                appState.data.startRun(workflowName: workflow.name, app: workflow.app)
                onClose()
            }
            PButton("", icon: "xmark",
                    variant: .ghost, size: .icon, action: onClose)
        }
        .padding(.horizontal, 18)
        .padding(.vertical, 14)
    }

    private var tabsRow: some View {
        HStack(spacing: 0) {
            ForEach(Tab.allCases) { t in
                DrawerTabButton(label: t.label, active: tab == t) { tab = t }
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 12)
    }
}

private struct DrawerTabButton: View {
    let label: String
    let active: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(spacing: 6) {
                Text(label)
                    .font(PFont.ui(12, weight: active ? .semibold : .medium))
                    .foregroundStyle(active ? PColor.fg0 : PColor.fg2)
                    .padding(.horizontal, 10)
                    .padding(.top, 12)
                Rectangle()
                    .fill(active ? PColor.signal : .clear)
                    .frame(height: 2)
            }
        }
        .buttonStyle(.plain)
    }
}

private struct DrawerOverview: View {
    let wf: WorkflowEnriched

    var body: some View {
        VStack(alignment: .leading, spacing: PSpace.l) {
            Text(wf.desc)
                .font(PFont.ui(12.5))
                .foregroundStyle(PColor.fg1)
                .fixedSize(horizontal: false, vertical: true)

            VStack(spacing: 0) {
                kvRow("Schedule") {
                    if let s = wf.schedule {
                        Chip(text: s.human, tone: .signal, dot: true)
                    } else {
                        Text("Not scheduled")
                            .font(PFont.ui(12))
                            .foregroundStyle(PColor.fg3)
                    }
                }
                divider
                kvRow("Next run") {
                    Text(wf.schedule?.nextRun ?? "—")
                        .font(PFont.mono(12))
                        .foregroundStyle(PColor.fg0)
                }
                divider
                kvRow("Avg duration") {
                    Text(wf.avgDuration ?? "—")
                        .font(PFont.mono(12))
                        .foregroundStyle(PColor.fg0)
                }
                divider
                kvRow("Avg cost") {
                    Text(wf.avgCost.map { "$\(String(format: "%.3f", $0))" } ?? "—")
                        .font(PFont.mono(12))
                        .foregroundStyle(PColor.fg0)
                }
                divider
                kvRow("Success rate") {
                    Text(successRate)
                        .font(PFont.mono(12))
                        .foregroundStyle(PColor.fg0)
                }
            }
            .background(PColor.bg2)
            .overlay(
                RoundedRectangle(cornerRadius: PRadius.lg)
                    .stroke(PColor.lineSoft, lineWidth: 0.5)
            )
            .clipShape(RoundedRectangle(cornerRadius: PRadius.lg))

            PCard {
                VStack(alignment: .leading, spacing: PSpace.s) {
                    Text("Last 12 runs").kicker()
                    Sparkline(data: wf.health, width: 320, height: 28)
                }
            }
        }
    }

    private var divider: some View {
        Rectangle().fill(PColor.lineSoft).frame(height: 0.5)
    }

    private func kvRow<V: View>(_ key: String, @ViewBuilder value: () -> V) -> some View {
        HStack {
            Text(key)
                .font(PFont.ui(12.5))
                .foregroundStyle(PColor.fg2)
            Spacer()
            value()
        }
        .padding(.horizontal, PSpace.l)
        .padding(.vertical, PSpace.m)
    }

    private var successRate: String {
        let total = wf.okCount + wf.failCount
        guard total > 0 else { return "—" }
        return "\(Int((Double(wf.okCount) / Double(total)) * 100))%"
    }
}

private struct DrawerSchedule: View {
    @EnvironmentObject var appState: AppState
    let wf: WorkflowEnriched
    @State private var nlText: String = ""
    @State private var parsedCron: String = ""
    @State private var scheduleError: String? = nil
    @State private var savedHint: String? = nil
    @State private var parsing: Bool = false
    @State private var saving: Bool = false

    var body: some View {
        VStack(alignment: .leading, spacing: PSpace.l) {
            PCard {
                VStack(alignment: .leading, spacing: PSpace.m) {
                    Text("When should this run?")
                        .font(PFont.display(14, weight: .semibold))
                        .foregroundStyle(PColor.fg0)

                    TextField("e.g. every weekday at 8am", text: $nlText)
                        .textFieldStyle(.plain)
                        .font(PFont.ui(13))
                        .foregroundStyle(PColor.fg0)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 8)
                        .background(PColor.bg1)
                        .overlay(
                            RoundedRectangle(cornerRadius: PRadius.md)
                                .stroke(PColor.line, lineWidth: 0.5)
                        )
                        .clipShape(RoundedRectangle(cornerRadius: PRadius.md))

                    HStack(spacing: PSpace.s) {
                        PButton(parsing ? "Parsing…" : "Parse", icon: "sparkles",
                                variant: .primary, size: .small) {
                            Task { await parseCadence() }
                        }
                        .disabled(parsing || nlText.isEmpty)
                        Text("Claude turns this into cron")
                            .font(PFont.ui(12))
                            .foregroundStyle(PColor.fg3)
                    }

                    VStack(alignment: .leading, spacing: 4) {
                        Text("Cron expression").kicker()
                        Text(parsedCron.isEmpty ? (wf.schedule?.cron ?? "0 8 * * 1-5") : parsedCron)
                            .font(PFont.mono(13))
                            .foregroundStyle(PColor.fg0)
                            .padding(.bottom, 4)
                        Text("Next 3 runs").kicker()
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Mon Apr 20, 8:00 AM")
                            Text("Tue Apr 21, 8:00 AM")
                            Text("Wed Apr 22, 8:00 AM")
                        }
                        .font(PFont.mono(12))
                        .foregroundStyle(PColor.fg3)
                    }
                    .padding(PSpace.m)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(PColor.bg1)
                    .overlay(
                        RoundedRectangle(cornerRadius: PRadius.md)
                            .stroke(PColor.lineSoft, lineWidth: 0.5)
                    )
                    .clipShape(RoundedRectangle(cornerRadius: PRadius.md))
                }
            }

            HStack(spacing: PSpace.s) {
                PButton(saving ? "Saving…" : "Save schedule", icon: "checkmark",
                        variant: .primary, size: .small) {
                    Task { await saveSchedule() }
                }
                .disabled(saving || effectiveCron.isEmpty)
                if existingScheduleID != nil {
                    PButton("Remove schedule",
                            variant: .danger, size: .small) {
                        Task { await removeSchedule() }
                    }
                }
                if let savedHint {
                    Chip(text: savedHint, tone: .ok, dot: true)
                }
            }

            if let scheduleError {
                Text(scheduleError)
                    .font(PFont.ui(11.5))
                    .foregroundStyle(PColor.bad)
                    .lineLimit(3)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .onAppear {
            if nlText.isEmpty { nlText = wf.schedule?.human ?? "every weekday at 8am" }
        }
    }

    private var effectiveCron: String {
        parsedCron.isEmpty ? (wf.schedule?.cron ?? "") : parsedCron
    }

    private var existingScheduleID: String? {
        appState.data.schedules.first(where: { $0.workflowName == wf.name })?.id
    }

    private func parseCadence() async {
        guard !nlText.isEmpty, !parsing else { return }
        parsing = true
        defer { parsing = false }
        do {
            let r = try await appState.client.callOnce(method: "schedule.parse_cadence",
                                                       params: ["text": nlText])
            if let c = r["cron_expr"] as? String {
                parsedCron = c
                scheduleError = nil
            } else if let e = r["error"] as? String {
                scheduleError = e
            }
        } catch {
            scheduleError = "\(error)"
        }
    }

    private func saveSchedule() async {
        let cron = effectiveCron
        guard !cron.isEmpty, !saving else { return }
        saving = true
        defer { saving = false }
        do {
            let r = try await appState.client.callOnce(
                method: "schedule.create",
                params: ["workflow_name": wf.name, "cron_expr": cron])
            if let _ = r["job_id"] as? String {
                scheduleError = nil
                savedHint = "Saved"
                await appState.data.refreshSchedules()
                DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
                    savedHint = nil
                }
            } else if let e = r["error"] as? String {
                scheduleError = e
            }
        } catch {
            scheduleError = "\(error)"
        }
    }

    private func removeSchedule() async {
        guard let id = existingScheduleID else { return }
        do {
            _ = try await appState.client.callOnce(method: "schedule.delete",
                                                   params: ["job_id": id])
            await appState.data.refreshSchedules()
            scheduleError = nil
        } catch {
            scheduleError = "\(error)"
        }
    }
}

private struct DrawerHistory: View {
    @EnvironmentObject var appState: AppState
    let wf: WorkflowEnriched

    private var runs: [RunEnriched] {
        appState.data.runs.filter { $0.workflowName == wf.name }
    }

    var body: some View {
        if runs.isEmpty {
            Text("No runs yet for this workflow.")
                .font(PFont.ui(12.5))
                .foregroundStyle(PColor.fg3)
                .frame(maxWidth: .infinity, alignment: .center)
                .padding(PSpace.l)
        } else {
            VStack(spacing: 0) {
                ForEach(Array(runs.enumerated()), id: \.element.id) { idx, r in
                    if idx > 0 {
                        Rectangle().fill(PColor.lineSoft).frame(height: 0.5)
                    }
                    runRow(r)
                }
            }
            .background(PColor.bg2)
            .overlay(
                RoundedRectangle(cornerRadius: PRadius.lg)
                    .stroke(PColor.lineSoft, lineWidth: 0.5)
            )
            .clipShape(RoundedRectangle(cornerRadius: PRadius.lg))
        }
    }

    private func runRow(_ r: RunEnriched) -> some View {
        HStack(spacing: PSpace.m) {
            Chip(text: r.status.rawValue, tone: chipTone(for: r.status), dot: true)
            VStack(alignment: .leading, spacing: 2) {
                Text(r.humanMsg)
                    .font(PFont.ui(12.5))
                    .foregroundStyle(PColor.fg0)
                    .lineLimit(2)
                Text(r.at)
                    .font(PFont.mono(10.5))
                    .foregroundStyle(PColor.fg3)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            Text("$\(String(format: "%.3f", r.cost))")
                .font(PFont.mono(11))
                .foregroundStyle(PColor.fg3)
            PButton("", icon: "chevron.right",
                    variant: .ghost, size: .icon, action: {})
        }
        .padding(.horizontal, PSpace.l)
        .padding(.vertical, PSpace.m)
    }
}

private func chipTone(for status: RunEnriched.Status) -> Chip.Tone {
    switch status {
    case .success: return .ok
    case .failed: return .bad
    case .running: return .signal
    case .aborted, .skipped: return .warn
    }
}

private struct DrawerYaml: View {
    let wf: WorkflowEnriched

    private var content: String {
        let name = wf.id.replacingOccurrences(of: "wf_", with: "")
        return """
        name: \(name)
        app: \(wf.app)
        description: \(wf.desc)
        steps:
          - open_app: \(wf.app)
          - wait_for: "Dashboard"
          - tap: "Primary action"
          - read: value
        """
    }

    private var lines: [String] { content.components(separatedBy: "\n") }

    var body: some View {
        HStack(alignment: .top, spacing: 0) {
            VStack(alignment: .trailing, spacing: 2) {
                ForEach(Array(lines.enumerated()), id: \.offset) { idx, _ in
                    Text("\(idx + 1)")
                        .font(PFont.mono(12.5))
                        .foregroundStyle(PColor.fg3)
                }
            }
            .padding(.vertical, 12)
            .padding(.horizontal, 10)
            .frame(minWidth: 36, alignment: .trailing)
            .background(PColor.bg1)

            VStack(alignment: .leading, spacing: 2) {
                ForEach(Array(lines.enumerated()), id: \.offset) { _, line in
                    Text(line.isEmpty ? " " : line)
                        .font(PFont.mono(12.5))
                        .foregroundStyle(PColor.fg0)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
            .padding(.vertical, 12)
            .padding(.horizontal, 12)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .frame(height: 400)
        .background(PColor.bg0)
        .overlay(
            RoundedRectangle(cornerRadius: PRadius.md)
                .stroke(PColor.lineSoft, lineWidth: 0.5)
        )
        .clipShape(RoundedRectangle(cornerRadius: PRadius.md))
    }
}

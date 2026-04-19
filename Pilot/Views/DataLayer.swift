import Foundation
import SwiftUI

// Shared data layer the revamped views read from. Pulls real records from the
// daemon, joins them into the `WorkflowEnriched` / `RunEnriched` shapes the UI
// expects, and exposes a `LiveRunsStore` for active workflow.run streams.

@MainActor
final class PilotData: ObservableObject {
    @Published var workflows: [WorkflowEnriched] = []
    @Published var runs: [RunEnriched] = []
    @Published var schedules: [ScheduleRow] = []
    @Published var usage: UsageSummary = .empty
    @Published var health: SystemHealth = .empty
    @Published var loadError: String? = nil
    @Published var liveRuns: [LiveRun] = []

    weak var appState: AppState?

    struct ScheduleRow: Identifiable, Hashable {
        let id: String
        let workflowName: String
        let cron: String
        let nextRunISO: String
        let enabled: Bool
    }

    struct UsageSummary: Hashable {
        var dailyCost: Double
        var dailyBudget: Double
        var monthlyCost: Double
        var monthlyBudget: Double
        var perTaskBudget: Double
        var totalCalls: Int
        static let empty = UsageSummary(dailyCost: 0, dailyBudget: 5,
                                        monthlyCost: 0, monthlyBudget: 50,
                                        perTaskBudget: 1, totalCalls: 0)
    }

    struct SystemHealth: Hashable {
        var status: String
        var version: String
        var pid: Int
        var uptime: String
        var platform: String
        var apiKeyOK: Bool
        // (ok, detail) per probe key — populated by health.full_check.
        var probes: [String: (ok: Bool, detail: String)]
        var lastCheckedAt: Date?

        static let empty = SystemHealth(status: "—", version: "—", pid: 0,
                                        uptime: "—", platform: "—",
                                        apiKeyOK: false, probes: [:], lastCheckedAt: nil)

        // Hashable manual: tuples don't conform.
        static func == (l: SystemHealth, r: SystemHealth) -> Bool {
            l.status == r.status && l.version == r.version && l.pid == r.pid
                && l.uptime == r.uptime && l.platform == r.platform
                && l.apiKeyOK == r.apiKeyOK && l.lastCheckedAt == r.lastCheckedAt
                && l.probes.keys.sorted() == r.probes.keys.sorted()
        }
        func hash(into h: inout Hasher) {
            h.combine(status); h.combine(version); h.combine(pid)
            h.combine(uptime); h.combine(platform); h.combine(apiKeyOK)
        }
    }

    struct LiveRun: Identifiable, Hashable {
        let id: String                 // request_id we generated; replaced with run_id on `started` event
        var runID: String?
        let workflowName: String
        let workflowApp: String
        var status: RunEnriched.Status = .running
        var humanMsg: String = "starting…"
        var elapsed: String = "0:00"
        var steps: [RunEnriched.Step] = []
        var lastShotB64: String? = nil
        var startedAt: Date = Date()
        var cost: Double = 0
        var finalSummary: String = ""
    }

    func bind(to appState: AppState) {
        self.appState = appState
    }

    // MARK: - Load fan-out

    func refreshAll() async {
        loadError = nil
        // Serial — the daemon handles one request at a time per connection,
        // and the Swift NWConnection over Unix sockets gets confused if we
        // fan out 5 callOnces against a single shared socket simultaneously.
        await refreshHealth()
        await refreshUsage()
        await refreshSchedules()
        await refreshWorkflows()
        await refreshRuns()
    }

    func refreshWorkflows() async {
        guard let client = appState?.client else { return }
        if !client.isConnected { await client.connect() }
        do {
            let r = try await client.callOnce(method: "workflow.list")
            let raws = r["workflows"] as? [[String: Any]] ?? []
            // We need schedules + runs to compute the per-workflow enrichment.
            // Both are loaded by sibling refresh calls; recompute on each.
            self.workflows = raws.compactMap { Self.mergeWorkflow($0,
                                                                  schedules: self.schedules,
                                                                  runs: self.runs) }
        } catch {
            self.loadError = "workflow.list: \(error)"
        }
    }

    func refreshRuns(limit: Int = 100) async {
        guard let client = appState?.client else { return }
        if !client.isConnected { await client.connect() }
        do {
            let r = try await client.callOnce(method: "run.list", params: ["limit": limit])
            let raws = r["runs"] as? [[String: Any]] ?? []
            let workflowAppByID: [String: String] = Dictionary(
                uniqueKeysWithValues: self.workflows.map { ($0.name, $0.app) })
            self.runs = raws.map { Self.runFrom($0, workflowAppLookup: workflowAppByID) }
            // Re-enrich workflows with new run history.
            let names = Set(self.workflows.map(\.name))
            self.workflows = self.workflows.map { wf in
                Self.applyRunHistory(to: wf, allRuns: self.runs)
            }
            _ = names
        } catch {
            self.loadError = "run.list: \(error)"
        }
    }

    func refreshSchedules() async {
        guard let client = appState?.client else { return }
        if !client.isConnected { await client.connect() }
        do {
            let r = try await client.callOnce(method: "schedule.list")
            let raws = r["jobs"] as? [[String: Any]] ?? []
            self.schedules = raws.map {
                ScheduleRow(
                    id: ($0["id"] as? String) ?? UUID().uuidString,
                    workflowName: ($0["name"] as? String) ?? "—",
                    cron: ($0["trigger"] as? String) ?? "",
                    nextRunISO: ($0["next_run_time"] as? String) ?? "",
                    enabled: ($0["enabled"] as? Bool) ?? true
                )
            }
            // Re-merge schedules into workflows.
            self.workflows = self.workflows.map {
                Self.applySchedule(to: $0, schedules: self.schedules)
            }
        } catch {
            self.loadError = "schedule.list: \(error)"
        }
    }

    func refreshUsage() async {
        guard let client = appState?.client else { return }
        if !client.isConnected { await client.connect() }
        if let r = try? await client.callOnce(method: "usage.summary") {
            self.usage = UsageSummary(
                dailyCost: (r["daily_cost"] as? Double) ?? 0,
                dailyBudget: (r["daily_budget"] as? Double) ?? 5,
                monthlyCost: (r["monthly_cost"] as? Double) ?? 0,
                monthlyBudget: (r["monthly_budget"] as? Double) ?? 50,
                perTaskBudget: (r["per_task_budget"] as? Double) ?? 1,
                totalCalls: (r["total_calls"] as? Int) ?? 0
            )
        }
    }

    func refreshHealth(deep: Bool = false) async {
        guard let client = appState?.client else { return }
        if !client.isConnected { await client.connect() }
        if let h = try? await client.callOnce(method: "health.check") {
            self.health.status = (h["status"] as? String) ?? "ok"
            self.health.version = (h["version"] as? String) ?? "—"
            self.health.pid = (h["pid"] as? Int) ?? 0
            if let s = h["uptime_s"] as? Double {
                self.health.uptime = Self.uptimeLabel(s)
            }
            self.health.platform = (h["platform"] as? String) ?? "—"
            self.health.apiKeyOK = (h["anthropic_api_key_set"] as? Bool) ?? false
            self.health.lastCheckedAt = Date()
        }
        if deep {
            if let f = try? await client.callOnce(method: "health.full_check") {
                var probes: [String: (Bool, String)] = [:]
                for (k, v) in f {
                    // Daemon returns probe state as either [bool, string] or {available, detail}.
                    if let arr = v as? [Any], let ok = arr.first as? Bool {
                        let d = (arr.count > 1 ? (arr[1] as? String) : nil) ?? ""
                        probes[k] = (ok, d)
                    } else if let dict = v as? [String: Any], let ok = dict["available"] as? Bool {
                        probes[k] = (ok, (dict["detail"] as? String) ?? "")
                    } else if let b = v as? Bool {
                        probes[k] = (b, "")
                    }
                }
                self.health.probes = probes
            }
        }
    }

    // MARK: - Live runs (workflow.run streaming)

    func startRun(workflowName: String, app: String) {
        guard let client = appState?.client else { return }
        let live = LiveRun(id: UUID().uuidString, runID: nil,
                           workflowName: workflowName, workflowApp: app)
        liveRuns.insert(live, at: 0)
        let liveID = live.id

        Task { @MainActor [weak self] in
            guard let self else { return }
            if !client.isConnected { await client.connect() }
            do {
                let stream = try client.call(method: "workflow.run",
                                             params: ["name": workflowName])
                for try await frame in stream {
                    self.applyFrame(frame, to: liveID)
                }
            } catch {
                self.markRunErrored(liveID, msg: "\(error)")
            }
            // Refresh past-runs table when the stream finishes.
            await self.refreshRuns()
            // Drop the live entry after a short tail so the user sees the final state.
            try? await Task.sleep(nanoseconds: 4_000_000_000)
            self.liveRuns.removeAll { $0.id == liveID }
        }
    }

    func cancelLiveRun(_ liveID: String) async {
        guard let live = liveRuns.first(where: { $0.id == liveID }),
              let runID = live.runID,
              let client = appState?.client else { return }
        _ = try? await client.callOnce(method: "run.abort", params: ["run_id": runID])
        markRunErrored(liveID, msg: "aborted")
    }

    private func applyFrame(_ frame: [String: Any], to liveID: String) {
        guard let idx = liveRuns.firstIndex(where: { $0.id == liveID }) else { return }
        let event = (frame["event"] as? String) ?? ""
        var live = liveRuns[idx]
        let elapsed = Int(Date().timeIntervalSince(live.startedAt))
        live.elapsed = String(format: "%d:%02d", elapsed / 60, elapsed % 60)

        switch event {
        case "started":
            live.runID = frame["run_id"] as? String
            live.steps.append(.init(t: timeStamp(), kind: .started, msg: "started workflow"))
        case "step":
            let n = (frame["step"] as? Int) ?? 0
            let kind = (frame["kind"] as? String) ?? "?"
            live.humanMsg = "step \(n + 1): \(kind)"
            live.steps.append(.init(t: timeStamp(), kind: .step, msg: "[\(n)] \(kind)"))
        case "screenshot":
            if let b64 = frame["image_b64"] as? String {
                live.lastShotB64 = b64
            }
            if let meta = frame["meta"] as? [String: Any],
               let kind = meta["kind"] as? String {
                live.steps.append(.init(t: timeStamp(), kind: .shot, msg: "📸 \(kind)"))
            }
        case "done":
            let s = (frame["status"] as? String) ?? "success"
            live.status = RunEnriched.Status(rawValue: s) ?? .success
            live.finalSummary = (frame["summary"] as? String) ?? ""
            live.steps.append(.init(t: timeStamp(), kind: .done,
                                    msg: "✓ \(s) — \(live.finalSummary)"))
        case "failed", "aborted":
            live.status = RunEnriched.Status(rawValue: event) ?? .failed
            let msg = (frame["error"] as? String) ?? (frame["summary"] as? String) ?? ""
            live.finalSummary = msg
            live.steps.append(.init(t: timeStamp(), kind: .failed, msg: "✗ \(event) — \(msg)"))
        case "error":
            live.status = .failed
            let msg = (frame["error"] as? String) ?? "unknown"
            live.finalSummary = msg
            live.steps.append(.init(t: timeStamp(), kind: .failed, msg: "✗ \(msg)"))
        default:
            break
        }
        liveRuns[idx] = live
    }

    private func markRunErrored(_ liveID: String, msg: String) {
        guard let idx = liveRuns.firstIndex(where: { $0.id == liveID }) else { return }
        liveRuns[idx].status = .failed
        liveRuns[idx].finalSummary = msg
    }

    // MARK: - Diagnose (Claude-drafted error summary, cached on the run row)

    /// Calls run.diagnose and returns a Claude-drafted human summary + suggestion.
    func diagnose(runID: String) async -> (humanMsg: String?, suggestion: String?) {
        guard let client = appState?.client else { return (nil, nil) }
        if !client.isConnected { await client.connect() }
        do {
            let r = try await client.callOnce(method: "run.diagnose",
                                              params: ["run_id": runID])
            return ((r["summary"] as? String) ?? (r["human"] as? String),
                    (r["suggestion"] as? String) ?? (r["fix"] as? String))
        } catch {
            return (nil, nil)
        }
    }

    // MARK: - Workflow merge helpers

    private static func mergeWorkflow(_ raw: [String: Any],
                                      schedules: [ScheduleRow],
                                      runs: [RunEnriched]) -> WorkflowEnriched? {
        guard let id = raw["id"] as? String, let name = raw["name"] as? String else {
            return nil
        }
        let app = (raw["app"] as? String) ?? "—"
        let desc = (raw["description"] as? String) ?? ""
        let last = (raw["last_run_at"] as? String)
        let okCount = (raw["success_count"] as? Int) ?? 0
        let runCount = (raw["run_count"] as? Int) ?? 0
        let failCount = max(0, runCount - okCount)

        let sched = schedules.first { $0.workflowName == name }
        let scheduleHint: WorkflowEnriched.ScheduleHint? = sched.map {
            .init(human: humanize(cron: $0.cron),
                  cron: $0.cron,
                  nextRun: nicenextrun($0.nextRunISO),
                  enabled: $0.enabled)
        }

        let myRuns = runs.filter { $0.workflowName == name }
        let health = sparkline(from: myRuns, slots: 12)

        let avgCost = myRuns.isEmpty ? nil :
            (myRuns.map(\.cost).reduce(0, +) / Double(myRuns.count))

        return WorkflowEnriched(
            id: id, name: name, app: app, desc: desc, last: last,
            health: health,
            okCount: okCount, failCount: failCount,
            schedule: scheduleHint,
            avgCost: avgCost,
            avgDuration: myRuns.compactMap(\.duration).first
        )
    }

    private static func applySchedule(to wf: WorkflowEnriched,
                                      schedules: [ScheduleRow]) -> WorkflowEnriched {
        let sched = schedules.first { $0.workflowName == wf.name }
        let hint: WorkflowEnriched.ScheduleHint? = sched.map {
            .init(human: humanize(cron: $0.cron),
                  cron: $0.cron,
                  nextRun: nicenextrun($0.nextRunISO),
                  enabled: $0.enabled)
        }
        return WorkflowEnriched(
            id: wf.id, name: wf.name, app: wf.app, desc: wf.desc, last: wf.last,
            health: wf.health, okCount: wf.okCount, failCount: wf.failCount,
            schedule: hint, avgCost: wf.avgCost, avgDuration: wf.avgDuration)
    }

    private static func applyRunHistory(to wf: WorkflowEnriched,
                                        allRuns: [RunEnriched]) -> WorkflowEnriched {
        let myRuns = allRuns.filter { $0.workflowName == wf.name }
        let health = sparkline(from: myRuns, slots: 12)
        let avgCost = myRuns.isEmpty ? wf.avgCost :
            (myRuns.map(\.cost).reduce(0, +) / Double(myRuns.count))
        return WorkflowEnriched(
            id: wf.id, name: wf.name, app: wf.app, desc: wf.desc, last: wf.last,
            health: health, okCount: wf.okCount, failCount: wf.failCount,
            schedule: wf.schedule, avgCost: avgCost,
            avgDuration: myRuns.compactMap(\.duration).first ?? wf.avgDuration)
    }

    private static func sparkline(from runs: [RunEnriched], slots: Int) -> [Int] {
        let recent = Array(runs.prefix(slots))
        var bars = recent.map { $0.status == .success ? 1 : ($0.status == .failed ? -1 : 0) }
        // Pad left with 0s so the sparkline always has `slots` columns.
        while bars.count < slots { bars.append(0) }
        return Array(bars.prefix(slots))
    }

    private static func runFrom(_ raw: [String: Any],
                                workflowAppLookup: [String: String]) -> RunEnriched {
        let id = (raw["id"] as? String) ?? UUID().uuidString
        let workflowName = (raw["workflow_id"] as? String)
            ?? (raw["workflow_name"] as? String) ?? "—"
        let app = workflowAppLookup[workflowName] ?? "—"
        let s = (raw["status"] as? String) ?? "—"
        let status = RunEnriched.Status(rawValue: s) ?? .failed
        let summary = (raw["summary"] as? String) ?? ""
        let started = (raw["started_at"] as? String) ?? ""
        let ended = (raw["ended_at"] as? String) ?? ""
        let cost = (raw["cost_usd"] as? Double) ?? 0

        return RunEnriched(
            id: id, workflowName: workflowName, workflowApp: app,
            status: status,
            at: String(started.prefix(19)),
            humanMsg: summary.isEmpty ? "(no summary)" : summary,
            rawError: status == .failed ? summary : nil,
            stepLabel: nil,
            suggestion: nil,
            cost: cost,
            duration: durationLabel(start: started, end: ended),
            elapsed: nil,
            steps: []
        )
    }

    // MARK: - Tiny formatters

    private static func uptimeLabel(_ s: Double) -> String {
        if s < 60 { return String(format: "%.0f s", s) }
        if s < 3600 { return String(format: "%.0f m", s / 60) }
        return String(format: "%.1f h", s / 3600)
    }

    private static func durationLabel(start: String, end: String) -> String? {
        guard !start.isEmpty, !end.isEmpty else { return nil }
        let f = ISO8601DateFormatter()
        guard let s = f.date(from: start) ?? f.date(from: start + "Z"),
              let e = f.date(from: end) ?? f.date(from: end + "Z") else { return nil }
        let secs = Int(e.timeIntervalSince(s))
        if secs < 60 { return "\(secs)s" }
        return String(format: "%dm %02ds", secs / 60, secs % 60)
    }

    private static func nicenextrun(_ iso: String) -> String {
        guard !iso.isEmpty else { return "—" }
        let f = ISO8601DateFormatter()
        guard let d = f.date(from: iso) ?? f.date(from: iso + "Z") else { return iso }
        let out = DateFormatter()
        out.dateFormat = "EEE MMM d, h:mma"
        return out.string(from: d)
    }

    private static func humanize(cron: String) -> String {
        // Heuristic only — the daemon's schedule.parse_cadence handles the inverse.
        // We just give a friendly display when the cron fits a common pattern.
        switch cron {
        case "0 8 * * 1-5":  return "every weekday at 8am"
        case "0 6 * * *":    return "every day at 6am"
        case "30 7 * * 1-5": return "weekdays 7:30am"
        case "0 22 * * *":   return "every evening at 10pm"
        default:             return cron
        }
    }

    private func timeStamp() -> String {
        let f = DateFormatter()
        f.dateFormat = "HH:mm:ss"
        return f.string(from: Date())
    }
}

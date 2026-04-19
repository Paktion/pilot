import Foundation

// Mock enrichment for fields the daemon doesn't yet expose.
// The revamped UI assumes per-workflow descriptions, sparkline data, embedded
// schedule, average duration/cost, and Claude-drafted error summaries — none of
// which the current Python daemon returns. This file fills those gaps client-side
// so the new views render with realistic content. Each TODO marks an RPC the
// daemon should grow before we ship for real.

struct WorkflowEnriched: Identifiable, Hashable {
    let id: String
    let name: String
    let app: String
    let desc: String
    let last: String?            // ISO-ish string for display only
    let health: [Int]            // last N runs, 1=ok / -1=fail / 0=no run
    let okCount: Int
    let failCount: Int
    let schedule: ScheduleHint?
    let avgCost: Double?
    let avgDuration: String?

    struct ScheduleHint: Hashable {
        let human: String
        let cron: String
        let nextRun: String
        let enabled: Bool
    }
}

struct RunEnriched: Identifiable, Hashable {
    enum Status: String { case running, success, failed, aborted, skipped }
    struct Step: Hashable {
        enum Kind: String { case started, step, shot, done, failed }
        let t: String
        let kind: Kind
        let msg: String
    }

    let id: String
    let workflowName: String
    let workflowApp: String
    let status: Status
    let at: String
    let humanMsg: String
    let rawError: String?
    let stepLabel: String?       // "read swipes remaining (step 3 of 4)"
    let suggestion: String?      // Claude-drafted fix
    let cost: Double
    let duration: String?
    let elapsed: String?
    let steps: [Step]
}

enum MockData {
    // TODO(daemon): replace with workflow.list result merged with schedule.list +
    // a new workflow.health(name=…) RPC returning last-N run summaries.
    static let workflows: [WorkflowEnriched] = [
        .init(id: "wf_osu",
              name: "Check OSU Dining Swipes",
              app: "Ohio State",
              desc: "Open the OSU app, grab remaining swipe count + account balance.",
              last: "2026-04-19T06:22",
              health: [1, 1, -1, 1, 1, -1, -1, 1, 1, -1, -1, -1],
              okCount: 0, failCount: 1,
              schedule: .init(human: "every weekday at 8am",
                              cron: "0 8 * * 1-5",
                              nextRun: "Mon Apr 20, 8:00am",
                              enabled: true),
              avgCost: 0.04, avgDuration: "38s"),
        .init(id: "wf_chipotle",
              name: "Reorder Chipotle Bowl",
              app: "Grubhub",
              desc: "Reorder my usual bowl from the nearest Chipotle.",
              last: nil,
              health: Array(repeating: 0, count: 12),
              okCount: 0, failCount: 0,
              schedule: nil, avgCost: nil, avgDuration: nil),
        .init(id: "wf_weather",
              name: "Check Today's Weather",
              app: "Weather",
              desc: "Read today's high/low and conditions. Post to the family group.",
              last: "2026-04-19T05:56",
              health: Array(repeating: -1, count: 12),
              okCount: 0, failCount: 2,
              schedule: .init(human: "every day at 6am",
                              cron: "0 6 * * *",
                              nextRun: "Tomorrow, 6:00am",
                              enabled: true),
              avgCost: nil, avgDuration: nil),
        .init(id: "wf_spotify",
              name: "Queue commute playlist",
              app: "Spotify",
              desc: "Open Spotify, start 'Morning Commute' playlist on the phone speaker.",
              last: "2026-04-18T07:30",
              health: Array(repeating: 1, count: 12),
              okCount: 14, failCount: 0,
              schedule: .init(human: "weekdays 7:30am",
                              cron: "30 7 * * 1-5",
                              nextRun: "Mon Apr 20, 7:30am",
                              enabled: true),
              avgCost: 0.012, avgDuration: "14s"),
        .init(id: "wf_notes",
              name: "Log daily journal entry",
              app: "Notes",
              desc: "Open Notes, append today's date and a blank template.",
              last: "2026-04-19T22:00",
              health: [1, 1, 1, 1, 1, 0, 1, 1, 1, 1, -1, 1],
              okCount: 22, failCount: 1,
              schedule: .init(human: "every evening at 10pm",
                              cron: "0 22 * * *",
                              nextRun: "Tonight, 10:00pm",
                              enabled: true),
              avgCost: 0.018, avgDuration: "22s"),
        .init(id: "wf_uber",
              name: "Request Uber to office",
              app: "Uber",
              desc: "Open Uber, request UberX from home to office, confirm.",
              last: nil,
              health: Array(repeating: 0, count: 12),
              okCount: 0, failCount: 0,
              schedule: nil, avgCost: nil, avgDuration: nil),
    ]

    // TODO(daemon): replace with run.list + a new run.summary(id=…) RPC that
    // returns the human message + suggested fix per failed run (Haiku-cached).
    static let runs: [RunEnriched] = [
        .init(id: "run_live",
              workflowName: "Check OSU Dining Swipes",
              workflowApp: "Ohio State",
              status: .running,
              at: "just now",
              humanMsg: "Reading swipe count…",
              rawError: nil,
              stepLabel: nil,
              suggestion: nil,
              cost: 0.012,
              duration: nil,
              elapsed: "0:14",
              steps: [
                .init(t: "08:30:02", kind: .started, msg: "started workflow"),
                .init(t: "08:30:04", kind: .step,    msg: "[1] open_app Ohio State"),
                .init(t: "08:30:07", kind: .shot,    msg: "📸 captured dashboard"),
                .init(t: "08:30:09", kind: .step,    msg: "[2] tap 'Dining'"),
                .init(t: "08:30:12", kind: .shot,    msg: "📸 captured dining page"),
                .init(t: "08:30:14", kind: .step,    msg: "[3] read swipes remaining"),
              ]),
        .init(id: "run_1",
              workflowName: "Check OSU Dining Swipes",
              workflowApp: "Ohio State",
              status: .failed,
              at: "2026-04-19 06:21:51",
              humanMsg: "Couldn't parse '68, 207' as a number",
              rawError: "ValueError: invalid literal for int() with base 10: '68, 207'",
              stepLabel: "read swipes remaining (step 3 of 4)",
              suggestion: "The OCR picked up a second number. Try narrowing the bounding box.",
              cost: 0.024, duration: "21s", elapsed: nil, steps: []),
        .init(id: "run_2",
              workflowName: "Check Today's Weather",
              workflowApp: "Weather",
              status: .failed,
              at: "2026-04-19 05:56:42",
              humanMsg: "Gave up waiting for the forecast text",
              rawError: "wait_for timed out: ['Today', 'H:', 'L:', '°']",
              stepLabel: "wait for forecast (step 2 of 3)",
              suggestion: "Weather app may not have loaded. Add a 2s delay after open_app.",
              cost: 0, duration: "12s", elapsed: nil, steps: []),
        .init(id: "run_3",
              workflowName: "Check Today's Weather",
              workflowApp: "Weather",
              status: .failed,
              at: "2026-04-19 05:52:11",
              humanMsg: "Controller dependency missing — can't run",
              rawError: "ModuleNotFoundError: No module named 'pyautogui'",
              stepLabel: "initialize controller",
              suggestion: "This is a Pilot daemon issue. Run Settings → Debug → Full system check.",
              cost: 0, duration: "1s", elapsed: nil, steps: []),
        .init(id: "run_4",
              workflowName: "Queue commute playlist",
              workflowApp: "Spotify",
              status: .success,
              at: "2026-04-18 07:30:08",
              humanMsg: "Playlist 'Morning Commute' started on phone",
              rawError: nil, stepLabel: nil, suggestion: nil,
              cost: 0.012, duration: "14s", elapsed: nil, steps: []),
        .init(id: "run_5",
              workflowName: "Log daily journal entry",
              workflowApp: "Notes",
              status: .success,
              at: "2026-04-18 22:00:14",
              humanMsg: "Created entry for 2026-04-18",
              rawError: nil, stepLabel: nil, suggestion: nil,
              cost: 0.018, duration: "19s", elapsed: nil, steps: []),
    ]

    // 30-day cost breakdown — Settings hero card. TODO(daemon): usage.byWorkflow(days=30).
    static let costByWorkflow: [(String, Double, String)] = [
        ("Log daily journal entry", 1.42, "Notes"),
        ("Queue commute playlist",  0.98, "Spotify"),
        ("Check OSU Dining Swipes", 0.53, "Ohio State"),
        ("Check Today's Weather",   0.22, "Weather"),
    ]
}

// Helpers reused across views.
enum TimeFmt {
    static func ago(_ iso: String?) -> String {
        guard let iso else { return "never run" }
        // Reference "now" matches the prototype mock for visual consistency.
        let fmt = ISO8601DateFormatter()
        fmt.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let now = ISO8601DateFormatter().date(from: "2026-04-19T08:30:00Z") ?? Date()
        // Accept either with or without fractional seconds / timezone.
        let lenient = ISO8601DateFormatter()
        lenient.formatOptions = [.withInternetDateTime]
        let then = fmt.date(from: iso + "Z")
            ?? lenient.date(from: iso + "Z")
            ?? lenient.date(from: iso)
            ?? Date()
        let diffMin = Int((now.timeIntervalSince(then)) / 60)
        if diffMin < 0 { return "scheduled" }
        if diffMin < 60 { return "\(diffMin)m ago" }
        if diffMin < 60 * 24 { return "\(diffMin / 60)h ago" }
        return "\(diffMin / (60 * 24))d ago"
    }
}

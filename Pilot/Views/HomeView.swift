import SwiftUI

struct HomeView: View {
    @EnvironmentObject var appState: AppState
    let navigateTo: (MainWindow.Nav) -> Void
    let openDrawer: (WorkflowEnriched) -> Void
    let onRunStarted: () -> Void

    private var upcoming: [WorkflowEnriched] {
        Array(
            appState.data.workflows
                .filter { $0.schedule != nil }
                .sorted { ($0.schedule?.nextRun ?? "") < ($1.schedule?.nextRun ?? "") }
                .prefix(5)
        )
    }

    private var failing: [RunEnriched] {
        Array(appState.data.runs.filter { $0.status == .failed }.prefix(3))
    }

    private var scheduledTodayCount: Int {
        appState.data.workflows.filter { $0.schedule != nil }.count
    }

    private var failingHero: WorkflowEnriched? {
        appState.data.workflows.first { $0.failCount > 0 && $0.okCount == 0 }
    }

    private var favorite: WorkflowEnriched? {
        appState.data.workflows.max(by: {
            ($0.okCount + $0.failCount) < ($1.okCount + $1.failCount)
        })
    }

    var body: some View {
        ScrollView {
            VStack(spacing: 16) {
                hero
                statTiles
                HStack(alignment: .top, spacing: 16) {
                    upcomingCard
                    failingCard
                }
                Color.clear.frame(height: 8)
            }
            .padding(24)
        }
        .background(PColor.bg1)
        .task { await appState.data.refreshAll() }
    }

    // ── Hero greeting ────────────────────────────────────────────
    private var hero: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(Self.greetingKicker()).kicker()
            Text("Good morning, Athin.")
                .font(PFont.display(26, weight: .semibold))
                .kerning(-0.6)
                .foregroundStyle(PColor.fg0)
                .padding(.top, 4)
                .padding(.bottom, 8)
            Text(heroSubline)
                .font(PFont.ui(14))
                .foregroundStyle(PColor.fg1)
                .lineSpacing(2)
                .frame(maxWidth: 560, alignment: .leading)
            HStack(spacing: 8) {
                PButton("New workflow", icon: "sparkles", variant: .primary) {
                    navigateTo(.author)
                }
                PButton("Run favorite", icon: "play.fill", variant: .ghost) {
                    if let fav = favorite {
                        appState.data.startRun(workflowName: fav.name, app: fav.app)
                        onRunStarted()
                    }
                }
            }
            .padding(.top, 18)
        }
        .padding(.horizontal, 28)
        .padding(.vertical, 26)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            ZStack {
                PColor.bg2
                LinearGradient(
                    gradient: Gradient(colors: [PColor.signalDim, .clear]),
                    startPoint: .topTrailing, endPoint: .center
                )
            }
        )
        .overlay(RoundedRectangle(cornerRadius: PRadius.lg)
            .stroke(PColor.lineSoft, lineWidth: 0.5))
        .clipShape(RoundedRectangle(cornerRadius: PRadius.lg))
    }

    private var heroSubline: String {
        var base = "\(scheduledTodayCount) workflows scheduled for today."
        if let f = failingHero {
            base += " The \(f.name) check has been failing — open Runs to see what."
        }
        return base
    }

    private static func greetingKicker() -> String {
        let f = DateFormatter()
        f.dateFormat = "EEE MMM d · h:mm a"
        return f.string(from: Date())
    }

    // ── Stat tiles ───────────────────────────────────────────────
    private var statTiles: some View {
        HStack(alignment: .top, spacing: 12) {
            StatTile(label: "Daemon") {
                AnyView(
                    HStack(spacing: 8) {
                        StatusDot(tone: appState.daemonConnected ? .ok : .bad)
                        Text(appState.daemonConnected ? "Connected" : "Offline")
                            .font(PFont.display(22, weight: .semibold))
                            .kerning(-0.4)
                            .foregroundStyle(appState.daemonConnected ? PColor.ok : PColor.bad)
                    }
                )
            } caption: {
                AnyView(
                    Text("uptime \(appState.data.health.uptime) · PID \(appState.data.health.pid)")
                        .font(PFont.mono(11.5))
                        .foregroundStyle(PColor.fg2)
                )
            }

            StatTile(label: "Today's spend") {
                AnyView(
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        Text(String(format: "$%.3f", appState.data.usage.dailyCost))
                            .font(PFont.display(22, weight: .semibold))
                            .kerning(-0.4)
                            .foregroundStyle(PColor.fg0)
                        Text(String(format: "/ $%.2f", appState.dailyBudget))
                            .font(PFont.display(15, weight: .regular))
                            .foregroundStyle(PColor.fg3)
                    }
                )
            } caption: {
                AnyView(
                    GeometryReader { geo in
                        ZStack(alignment: .leading) {
                            Capsule().fill(PColor.bg4).frame(height: 3)
                            Capsule().fill(PColor.signal)
                                .frame(width: geo.size.width * pct(spent: appState.data.usage.dailyCost,
                                                                   cap: appState.dailyBudget),
                                       height: 3)
                        }
                    }.frame(height: 3)
                )
            }

            StatTile(label: "Runs this week") {
                AnyView(
                    HStack(spacing: 8) {
                        Text("\(weekRuns.count)")
                            .font(PFont.display(22, weight: .semibold))
                            .kerning(-0.4)
                            .foregroundStyle(PColor.fg0)
                        Text("\(weekOK) ok")
                            .font(PFont.mono(11, weight: .medium))
                            .foregroundStyle(PColor.ok)
                        Text("\(weekFailed) failed")
                            .font(PFont.mono(11, weight: .medium))
                            .foregroundStyle(PColor.bad)
                    }
                )
            } caption: {
                AnyView(
                    Sparkline(data: weekSpark,
                              width: 140, height: 14)
                )
            }

            StatTile(label: "Permissions") {
                AnyView(
                    HStack(spacing: 8) {
                        StatusDot(tone: badPermCount == 0 ? .ok : .warn)
                        Text(badPermCount == 0 ? "All good" : "\(badPermCount) missing")
                            .font(PFont.display(22, weight: .semibold))
                            .kerning(-0.4)
                            .foregroundStyle(badPermCount == 0 ? PColor.ok : PColor.warn)
                    }
                )
            } caption: {
                AnyView(
                    Button { navigateTo(.settings) } label: {
                        Text("Open Settings →")
                            .font(PFont.ui(12))
                            .foregroundStyle(PColor.signal)
                    }
                    .buttonStyle(.plain)
                )
            }
        }
    }

    private var weekRuns: [RunEnriched] {
        let cutoff = Date().addingTimeInterval(-7 * 24 * 3600)
        let isoWithFracs = ISO8601DateFormatter()
        isoWithFracs.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let iso = ISO8601DateFormatter()
        iso.formatOptions = [.withInternetDateTime]
        let plain = DateFormatter()
        plain.dateFormat = "yyyy-MM-dd HH:mm:ss"
        return appState.data.runs.filter { r in
            let s = r.at
            let d = isoWithFracs.date(from: s + "Z")
                ?? iso.date(from: s + "Z")
                ?? iso.date(from: s)
                ?? plain.date(from: s)
            guard let d else { return false }
            return d >= cutoff
        }
    }

    private var weekOK: Int { weekRuns.filter { $0.status == .success }.count }
    private var weekFailed: Int { weekRuns.filter { $0.status == .failed }.count }

    private var weekSpark: [Int] {
        let recent = Array(appState.data.runs.prefix(14))
        var bars = recent.map { r -> Int in
            switch r.status {
            case .success: return 1
            case .failed:  return -1
            default:       return 0
            }
        }
        while bars.count < 14 { bars.append(0) }
        return Array(bars.prefix(14))
    }

    private var badPermCount: Int {
        appState.data.health.probes.values.filter { !$0.ok }.count
    }

    private func pct(spent: Double, cap: Double) -> CGFloat {
        guard cap > 0 else { return 0 }
        return min(1.0, CGFloat(spent / cap))
    }

    // ── Upcoming card ────────────────────────────────────────────
    private var upcomingCard: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text("Upcoming")
                    .font(PFont.display(14, weight: .semibold))
                    .kerning(-0.2)
                    .foregroundStyle(PColor.fg0)
                Spacer()
                PButton("View all", variant: .ghost, size: .small) {
                    navigateTo(.workflows)
                }
            }
            .padding(.bottom, 8)
            VStack(spacing: 0) {
                ForEach(upcoming) { wf in
                    UpcomingRow(wf: wf,
                                onOpen: { openDrawer(wf) },
                                onRun: {
                                    appState.data.startRun(workflowName: wf.name, app: wf.app)
                                    onRunStarted()
                                })
                    if wf.id != upcoming.last?.id {
                        Divider().background(PColor.lineSoft)
                    }
                }
            }
        }
        .padding(EdgeInsets(top: 16, leading: 18, bottom: 8, trailing: 4))
        .background(PColor.bg2)
        .overlay(RoundedRectangle(cornerRadius: PRadius.lg)
            .stroke(PColor.lineSoft, lineWidth: 0.5))
        .clipShape(RoundedRectangle(cornerRadius: PRadius.lg))
        .frame(maxWidth: .infinity)
    }

    private var failingCard: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text("Needs attention")
                    .font(PFont.display(14, weight: .semibold))
                    .kerning(-0.2)
                    .foregroundStyle(PColor.fg0)
                Spacer()
                PButton("All runs", variant: .ghost, size: .small) {
                    navigateTo(.runs)
                }
            }
            .padding(.bottom, 8)
            VStack(spacing: 0) {
                ForEach(failing) { run in
                    FailingRow(run: run, onReplay: {
                        appState.data.startRun(workflowName: run.workflowName, app: run.workflowApp)
                        onRunStarted()
                    })
                    if run.id != failing.last?.id {
                        Divider().background(PColor.lineSoft)
                    }
                }
            }
        }
        .padding(EdgeInsets(top: 16, leading: 18, bottom: 8, trailing: 4))
        .background(PColor.bg2)
        .overlay(RoundedRectangle(cornerRadius: PRadius.lg)
            .stroke(PColor.lineSoft, lineWidth: 0.5))
        .clipShape(RoundedRectangle(cornerRadius: PRadius.lg))
        .frame(maxWidth: .infinity)
    }
}

private struct StatTile: View {
    let label: String
    let value: () -> AnyView
    let caption: () -> AnyView

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label).kicker()
            value()
            caption()
                .padding(.top, 2)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(PColor.bg2)
        .overlay(RoundedRectangle(cornerRadius: PRadius.md)
            .stroke(PColor.lineSoft, lineWidth: 0.5))
        .clipShape(RoundedRectangle(cornerRadius: PRadius.md))
    }
}

private struct UpcomingRow: View {
    let wf: WorkflowEnriched
    let onOpen: () -> Void
    let onRun: () -> Void
    @State private var hovering = false

    var body: some View {
        Button(action: onOpen) {
            HStack(spacing: 10) {
                AppMark(app: wf.app, size: 26)
                VStack(alignment: .leading, spacing: 1) {
                    Text(wf.name)
                        .font(PFont.ui(12.5, weight: .medium))
                        .foregroundStyle(PColor.fg0)
                        .lineLimit(1)
                    if let s = wf.schedule {
                        Text(s.human)
                            .font(PFont.ui(11.5))
                            .foregroundStyle(PColor.fg2)
                            .lineLimit(1)
                    }
                }
                Spacer()
                Text(wf.schedule?.nextRun ?? "")
                    .font(PFont.mono(11))
                    .foregroundStyle(PColor.fg1)
                    .lineLimit(1)
                Button {
                    onRun()
                } label: {
                    Image(systemName: "play.fill")
                        .font(.system(size: 10))
                }
                .buttonStyle(.plain)
                .frame(width: 26, height: 22)
                .foregroundStyle(PColor.fg1)
                .overlay(RoundedRectangle(cornerRadius: 7)
                    .stroke(PColor.lineSoft, lineWidth: 0.5))
            }
            .padding(.vertical, 10)
            .padding(.trailing, 14)
            .background(hovering ? PColor.bg3 : .clear)
            .clipShape(RoundedRectangle(cornerRadius: 6))
        }
        .buttonStyle(.plain)
        .onHover { hovering = $0 }
    }
}

private struct FailingRow: View {
    let run: RunEnriched
    let onReplay: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Chip(text: "failed", tone: .bad, dot: true)
                .padding(.top, 2)
            VStack(alignment: .leading, spacing: 2) {
                Text(run.humanMsg)
                    .font(PFont.ui(12.5))
                    .foregroundStyle(PColor.fg0)
                    .lineLimit(2)
                Text("\(run.workflowName) · \(run.at)")
                    .font(PFont.mono(10.5))
                    .foregroundStyle(PColor.fg3)
                    .lineLimit(1)
            }
            Spacer()
            PButton("Replay", variant: .ghost, size: .small, action: onReplay)
        }
        .padding(.vertical, 10)
        .padding(.trailing, 14)
    }
}

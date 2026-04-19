import SwiftUI

struct WorkflowsView: View {
    let openDrawer: (WorkflowEnriched) -> Void
    let onAuthor: () -> Void
    let onRunStarted: () -> Void

    @EnvironmentObject var appState: AppState
    @State private var filter: Filter = .all
    @State private var refreshing: Bool = false

    private var workflowsList: [WorkflowEnriched] { appState.data.workflows }

    enum Filter: String, CaseIterable, Identifiable {
        case all, scheduled, failing, never
        var id: String { rawValue }
        var label: String {
            switch self {
            case .all: return "All"
            case .scheduled: return "Scheduled"
            case .failing: return "Failing"
            case .never: return "Never run"
            }
        }
    }

    private var counts: [Filter: Int] {
        let all = workflowsList
        return [
            .all: all.count,
            .scheduled: all.filter { $0.schedule != nil }.count,
            .failing: all.filter { $0.failCount > 0 && $0.okCount == 0 }.count,
            .never: all.filter { $0.last == nil }.count,
        ]
    }

    private var visible: [WorkflowEnriched] {
        workflowsList.filter { wf in
            switch filter {
            case .all: return true
            case .scheduled: return wf.schedule != nil
            case .failing: return wf.failCount > 0 && wf.okCount == 0
            case .never: return wf.last == nil
            }
        }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: PSpace.l) {
                filterRow
                contentBody
            }
            .padding(PSpace.xl)
        }
        .background(PColor.bg1)
        .task {
            if appState.data.workflows.isEmpty {
                await appState.data.refreshAll()
            }
        }
    }

    @ViewBuilder
    private var contentBody: some View {
        if appState.daemonConnected == false {
            offlineState
        } else if workflowsList.isEmpty {
            emptyState
        } else {
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 320), spacing: 14)],
                      spacing: 14) {
                ForEach(visible) { wf in
                    WFCard(wf: wf,
                           onOpen: { openDrawer(wf) },
                           onRun: {
                               appState.data.startRun(workflowName: wf.name, app: wf.app)
                               onRunStarted()
                           })
                }
            }
        }
    }

    private var emptyState: some View {
        VStack(spacing: PSpace.m) {
            Text("No workflows yet — use the Author tab to create one.")
                .font(PFont.ui(13))
                .foregroundStyle(PColor.fg2)
            PButton("New workflow", icon: "plus",
                    variant: .primary, size: .small, action: onAuthor)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, PSpace.xl * 2)
    }

    private var offlineState: some View {
        VStack(spacing: PSpace.m) {
            Text("Daemon offline — connect from sidebar")
                .font(PFont.ui(13))
                .foregroundStyle(PColor.fg2)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, PSpace.xl * 2)
    }

    private var filterRow: some View {
        HStack(spacing: PSpace.s) {
            HStack(spacing: 4) {
                ForEach(Filter.allCases) { f in
                    FilterTab(label: f.label,
                              count: counts[f] ?? 0,
                              active: filter == f,
                              action: { filter = f })
                }
            }
            Spacer()
            if refreshing {
                ProgressView()
                    .controlSize(.small)
                    .scaleEffect(0.7)
                    .frame(width: 16, height: 16)
            }
            PButton("Refresh", icon: "arrow.clockwise",
                    variant: .ghost, size: .small,
                    action: {
                        guard !refreshing else { return }
                        refreshing = true
                        Task {
                            await appState.data.refreshAll()
                            refreshing = false
                        }
                    })
            PButton("New workflow", icon: "plus",
                    variant: .primary, size: .small, action: onAuthor)
        }
    }
}

private struct FilterTab: View {
    let label: String
    let count: Int
    let active: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 6) {
                Text(label)
                    .font(PFont.ui(12, weight: .medium))
                Text("\(count)")
                    .font(PFont.mono(10.5, weight: .medium))
                    .foregroundStyle(active ? PColor.signalInk.opacity(0.7) : PColor.fg3)
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 5)
            .foregroundStyle(active ? PColor.signalInk : PColor.fg1)
            .background(active ? PColor.signal : PColor.bg2)
            .overlay(
                RoundedRectangle(cornerRadius: 7)
                    .stroke(active ? .clear : PColor.lineSoft, lineWidth: 0.5)
            )
            .clipShape(RoundedRectangle(cornerRadius: 7))
        }
        .buttonStyle(.plain)
    }
}

private struct WFCard: View {
    let wf: WorkflowEnriched
    let onOpen: () -> Void
    let onRun: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: PSpace.m) {
            HStack(alignment: .top, spacing: PSpace.m) {
                AppMark(app: wf.app, size: 34)
                VStack(alignment: .leading, spacing: 2) {
                    Text(wf.name)
                        .font(PFont.display(13.5, weight: .semibold))
                        .foregroundStyle(PColor.fg0)
                        .lineLimit(2)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    Text(wf.app)
                        .font(PFont.ui(11))
                        .foregroundStyle(PColor.fg2)
                }
                PButton("Run", icon: "play.fill",
                        variant: .primary, size: .small, action: onRun)
            }

            Text(wf.desc)
                .font(PFont.ui(12))
                .foregroundStyle(PColor.fg1)
                .lineLimit(2)
                .frame(maxWidth: .infinity, alignment: .leading)

            VStack(spacing: PSpace.s) {
                Rectangle()
                    .fill(PColor.lineSoft)
                    .frame(height: 0.5)
                metaRow(label: "Last run", content: { lastRunValue })
                metaRow(label: "Schedule", content: { scheduleValue })
            }

            HStack(spacing: PSpace.s) {
                Text("Last 12 runs").kicker()
                Sparkline(data: wf.health, width: 92, height: 16)
                Spacer()
                if let dur = wf.avgDuration, let cost = wf.avgCost {
                    Text("avg \(dur) · $\(String(format: "%.3f", cost))")
                        .font(PFont.mono(10.5))
                        .foregroundStyle(PColor.fg3)
                }
            }
        }
        .padding(PSpace.l)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(PColor.bg2)
        .overlay(
            RoundedRectangle(cornerRadius: PRadius.lg)
                .stroke(PColor.lineSoft, lineWidth: 0.5)
        )
        .clipShape(RoundedRectangle(cornerRadius: PRadius.lg))
        .contentShape(RoundedRectangle(cornerRadius: PRadius.lg))
        .onTapGesture { onOpen() }
    }

    private func metaRow<V: View>(label: String, @ViewBuilder content: () -> V) -> some View {
        HStack(alignment: .center, spacing: PSpace.s) {
            Text(label)
                .font(PFont.ui(11))
                .foregroundStyle(PColor.fg2)
                .frame(width: 64, alignment: .leading)
            content()
            Spacer(minLength: 0)
        }
    }

    private var lastRunValue: some View {
        let h = healthLabel()
        return HStack(spacing: PSpace.s) {
            Chip(text: h.text, tone: h.tone, dot: true)
            Text(TimeFmt.ago(wf.last))
                .font(PFont.ui(11))
                .foregroundStyle(PColor.fg3)
        }
    }

    @ViewBuilder
    private var scheduleValue: some View {
        if let s = wf.schedule {
            HStack(spacing: PSpace.s) {
                Chip(text: s.human, tone: .signal, dot: true)
                Text(s.nextRun)
                    .font(PFont.mono(10.5))
                    .foregroundStyle(PColor.fg3)
            }
        } else {
            Text("No schedule")
                .font(PFont.ui(11))
                .foregroundStyle(PColor.fg3)
        }
    }

    private func healthLabel() -> (text: String, tone: Chip.Tone) {
        if wf.okCount == 0 && wf.failCount == 0 { return ("Never run", .neutral) }
        let total = wf.okCount + wf.failCount
        let rate = Double(wf.okCount) / Double(total)
        if rate >= 1.0 { return ("\(wf.okCount)/\(total) ok", .ok) }
        if rate <= 0.0 { return ("\(wf.failCount) failing", .bad) }
        return ("\(wf.okCount)/\(total) ok", .warn)
    }
}

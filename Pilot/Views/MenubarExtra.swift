import SwiftUI
import AppKit

struct MenubarContent: View {
    @EnvironmentObject var appState: AppState
    @Environment(\.openWindow) private var openWindow

    private var nextScheduled: (WorkflowEnriched, WorkflowEnriched.ScheduleHint)? {
        appState.data.workflows
            .compactMap { wf in wf.schedule.map { (wf, $0) } }
            .sorted { $0.1.nextRun < $1.1.nextRun }
            .first
    }

    private var favorites: [WorkflowEnriched] {
        Array(
            appState.data.workflows
                .sorted { ($0.okCount + $0.failCount) > ($1.okCount + $1.failCount) }
                .prefix(3)
        )
    }

    private var recentFailure: RunEnriched? {
        appState.data.runs.first { $0.status == .failed }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            head
            Rectangle().fill(PColor.lineSoft).frame(height: 0.5)

            VStack(alignment: .leading, spacing: PSpace.s) {
                sectionHead("Next up", trailing: nextScheduled?.1.nextRun)
                nextCard
            }
            .padding(.horizontal, PSpace.m)
            .padding(.top, PSpace.m)

            VStack(alignment: .leading, spacing: 6) {
                sectionHead("Favorites", trailing: nil)
                favList
            }
            .padding(.horizontal, PSpace.m)
            .padding(.top, PSpace.m)

            if recentFailure != nil {
                VStack(alignment: .leading, spacing: 6) {
                    sectionHead("Recent", trailing: nil)
                    recentRow
                }
                .padding(.horizontal, PSpace.m)
                .padding(.top, PSpace.m)
                .padding(.bottom, PSpace.m)
            } else {
                Color.clear.frame(height: PSpace.m)
            }

            Rectangle().fill(PColor.lineSoft).frame(height: 0.5)
            actionsRow
        }
        .frame(width: 280)
        .task { await appState.data.refreshAll() }
    }

    private var head: some View {
        HStack(spacing: PSpace.s) {
            StatusDot(tone: appState.daemonConnected ? .signal : .bad)
            Text("Pilot")
                .font(PFont.ui(13, weight: .semibold))
                .foregroundStyle(PColor.fg0)
            Text(appState.daemonConnected ? "connected" : "offline")
                .font(PFont.mono(10.5))
                .foregroundStyle(PColor.fg2)
            Spacer()
            HStack(spacing: 0) {
                Text(String(format: "$%.3f", appState.data.usage.dailyCost))
                    .font(PFont.mono(11))
                    .foregroundStyle(PColor.fg0)
                Text(String(format: " / $%.0f", appState.data.usage.dailyBudget))
                    .font(PFont.mono(11))
                    .foregroundStyle(PColor.fg2)
            }
        }
        .padding(.horizontal, PSpace.m)
        .padding(.vertical, PSpace.s)
    }

    private func sectionHead(_ title: String, trailing: String?) -> some View {
        HStack {
            Text(title).kicker()
            Spacer()
            if let trailing {
                Text(trailing)
                    .font(PFont.mono(10))
                    .foregroundStyle(PColor.fg2)
            }
        }
    }

    @ViewBuilder
    private var nextCard: some View {
        if let (wf, sched) = nextScheduled {
            HStack(spacing: PSpace.s) {
                AppMark(app: wf.app, size: 22)
                VStack(alignment: .leading, spacing: 2) {
                    Text(wf.name)
                        .font(PFont.ui(12.5, weight: .medium))
                        .foregroundStyle(PColor.fg0)
                        .lineLimit(1)
                    Text(sched.nextRun)
                        .font(PFont.mono(10.5))
                        .foregroundStyle(PColor.fg2)
                }
                Spacer(minLength: 0)
                PButton("", icon: "play.fill", variant: .primary, size: .small) {
                    appState.data.startRun(workflowName: wf.name, app: wf.app)
                }
            }
            .padding(PSpace.s)
            .background(PColor.bg3)
            .clipShape(RoundedRectangle(cornerRadius: 8))
        } else {
            HStack {
                Text("No upcoming runs")
                    .font(PFont.ui(12))
                    .foregroundStyle(PColor.fg2)
                Spacer()
            }
            .padding(PSpace.s)
            .background(PColor.bg3)
            .clipShape(RoundedRectangle(cornerRadius: 8))
        }
    }

    private var favList: some View {
        VStack(spacing: 4) {
            ForEach(favorites) { w in
                HStack(spacing: PSpace.s) {
                    AppMark(app: w.app, size: 18)
                    Text(w.name)
                        .font(PFont.ui(12))
                        .foregroundStyle(PColor.fg0)
                        .lineLimit(1)
                    Spacer(minLength: 0)
                    Button {
                        appState.data.startRun(workflowName: w.name, app: w.app)
                    } label: {
                        Image(systemName: "play.fill")
                            .font(.system(size: 10, weight: .medium))
                            .foregroundStyle(PColor.fg2)
                    }
                    .buttonStyle(.plain)
                }
                .padding(.vertical, 3)
            }
        }
    }

    @ViewBuilder
    private var recentRow: some View {
        if let r = recentFailure {
            HStack(spacing: 6) {
                Chip(text: "failed", tone: .bad, dot: true)
                VStack(alignment: .leading, spacing: 1) {
                    Text(r.workflowName)
                        .font(PFont.ui(11.5, weight: .medium))
                        .foregroundStyle(PColor.fg0)
                        .lineLimit(1)
                    Text(r.humanMsg)
                        .font(PFont.ui(11))
                        .foregroundStyle(PColor.fg1)
                        .lineLimit(1)
                        .truncationMode(.tail)
                }
                Spacer(minLength: 0)
                Text(String(r.at.suffix(8)))
                    .font(PFont.mono(10))
                    .foregroundStyle(PColor.fg2)
            }
        }
    }

    private var actionsRow: some View {
        HStack(spacing: PSpace.s) {
            Button {
                openWindow(id: "pilot-main")
            } label: {
                Text("Open Pilot")
                    .font(PFont.ui(11.5, weight: .medium))
                    .foregroundStyle(PColor.fg1)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 5)
                    .overlay(
                        RoundedRectangle(cornerRadius: 7)
                            .stroke(PColor.lineSoft, lineWidth: 0.5)
                    )
            }
            .buttonStyle(.plain)

            PButton("Quit", variant: .ghost, size: .small) {
                NSApplication.shared.terminate(nil)
            }
        }
        .padding(.horizontal, PSpace.m)
        .padding(.vertical, PSpace.s)
    }
}

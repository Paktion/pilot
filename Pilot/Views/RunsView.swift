import SwiftUI

enum RunOrLive: Identifiable {
    case live(PilotData.LiveRun)
    case past(RunEnriched)

    var id: String {
        switch self {
        case .live(let l): return "live-" + l.id
        case .past(let r): return "past-" + r.id
        }
    }

    var rowID: String {
        switch self {
        case .live(let l): return l.id
        case .past(let r): return r.id
        }
    }

    var workflowName: String {
        switch self {
        case .live(let l): return l.workflowName
        case .past(let r): return r.workflowName
        }
    }

    var workflowApp: String {
        switch self {
        case .live(let l): return l.workflowApp
        case .past(let r): return r.workflowApp
        }
    }

    var status: RunEnriched.Status {
        switch self {
        case .live(let l): return l.status
        case .past(let r): return r.status
        }
    }

    var humanMsg: String {
        switch self {
        case .live(let l): return l.humanMsg
        case .past(let r): return r.humanMsg
        }
    }

    var trailingTime: String {
        switch self {
        case .live(let l): return l.elapsed
        case .past(let r): return r.duration ?? r.elapsed ?? ""
        }
    }
}

struct RunsView: View {
    @EnvironmentObject var appState: AppState
    @State private var selectedID: String? = nil
    @State private var filter: Filter = .all
    @State private var diagnoses: [String: (String?, String?)] = [:]

    enum Filter: String, CaseIterable, Identifiable {
        case all, failed, live
        var id: Self { self }
    }

    private var allRuns: [RunOrLive] {
        let live = appState.data.liveRuns.map { RunOrLive.live($0) }
        let past = appState.data.runs.map { RunOrLive.past($0) }
        switch filter {
        case .all:    return live + past
        case .live:   return live
        case .failed: return past.filter { $0.status == .failed }
        }
    }

    private static let dayFmt: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        return f
    }()

    private var todayString: String { Self.dayFmt.string(from: Date()) }

    private struct Group: Identifiable {
        let id: String
        let label: String
        let rows: [RunOrLive]
    }

    private var groups: [Group] {
        let liveRows = allRuns.filter { if case .live = $0 { return true } else { return false } }
        let pastRows = allRuns.compactMap { row -> RunOrLive? in
            if case .past = row { return row } else { return nil }
        }
        let today = todayString
        let todayRows = pastRows.filter {
            if case .past(let r) = $0 { return r.at.hasPrefix(today) }
            return false
        }
        let earlierRows = pastRows.filter {
            if case .past(let r) = $0 { return !r.at.hasPrefix(today) }
            return false
        }
        return [
            Group(id: "live",    label: "Live",    rows: liveRows),
            Group(id: "today",   label: "Today",   rows: todayRows),
            Group(id: "earlier", label: "Earlier", rows: earlierRows),
        ].filter { !$0.rows.isEmpty }
    }

    private var selected: RunOrLive? {
        if let id = selectedID, let m = allRuns.first(where: { $0.rowID == id }) {
            return m
        }
        return allRuns.first
    }

    var body: some View {
        HStack(alignment: .top, spacing: 0) {
            leftPane
                .frame(width: 320)
                .background(PColor.bg2)
                .overlay(alignment: .trailing) {
                    Rectangle().fill(PColor.lineSoft).frame(width: 0.5)
                }
            if appState.data.runs.isEmpty && appState.data.liveRuns.isEmpty {
                emptyState
            } else if let sel = selected {
                RunDetail(item: sel,
                          diagnoses: $diagnoses,
                          onCancel: { id in Task { await appState.data.cancelLiveRun(id) } },
                          diagnose: { rid in await appState.data.diagnose(runID: rid) })
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                    .background(PColor.bg1)
            } else {
                Spacer()
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .task { await appState.data.refreshRuns() }
        .onAppear {
            if selectedID == nil { selectedID = allRuns.first?.rowID }
        }
        .onChange(of: appState.data.liveRuns.count) { _, _ in
            if selectedID == nil { selectedID = allRuns.first?.rowID }
        }
    }

    private var emptyState: some View {
        VStack {
            Spacer()
            VStack(spacing: 8) {
                Text("No runs yet")
                    .font(PFont.display(16, weight: .semibold))
                    .foregroundStyle(PColor.fg0)
                Text("Start one from Workflows.")
                    .font(PFont.ui(12.5))
                    .foregroundStyle(PColor.fg2)
            }
            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    @ViewBuilder
    private var leftPane: some View {
        VStack(alignment: .leading, spacing: 0) {
            filterRow
                .padding(.horizontal, PSpace.m)
                .padding(.top, PSpace.m)
                .padding(.bottom, PSpace.s)
            ScrollView {
                VStack(alignment: .leading, spacing: PSpace.m) {
                    ForEach(groups) { g in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(g.label).kicker()
                                .padding(.horizontal, PSpace.m)
                                .padding(.bottom, 2)
                            VStack(spacing: 2) {
                                ForEach(g.rows) { row in runRow(row) }
                            }
                        }
                    }
                }
                .padding(.bottom, PSpace.m)
            }
        }
    }

    private var filterRow: some View {
        HStack(spacing: 4) {
            ForEach(Filter.allCases) { f in
                Button { filter = f } label: {
                    Text(f.rawValue)
                        .font(PFont.ui(11.5, weight: .medium))
                        .foregroundStyle(filter == f ? PColor.fg0 : PColor.fg2)
                        .padding(.horizontal, 10).padding(.vertical, 4)
                        .frame(maxWidth: .infinity)
                        .background(filter == f ? PColor.bg4 : Color.clear)
                        .clipShape(RoundedRectangle(cornerRadius: PRadius.sm))
                }
                .buttonStyle(.plain)
            }
        }
        .padding(3)
        .background(PColor.bg3)
        .overlay(RoundedRectangle(cornerRadius: PRadius.sm + 2).stroke(PColor.lineSoft, lineWidth: 0.5))
        .clipShape(RoundedRectangle(cornerRadius: PRadius.sm + 2))
    }

    @ViewBuilder
    private func runRow(_ row: RunOrLive) -> some View {
        let isSelected = selectedID == row.rowID
        Button { selectedID = row.rowID } label: {
            HStack(alignment: .top, spacing: 10) {
                AppMark(app: row.workflowApp, size: 22)
                VStack(alignment: .leading, spacing: 2) {
                    Text(row.workflowName)
                        .font(PFont.ui(12.5, weight: .medium))
                        .foregroundStyle(PColor.fg0).lineLimit(1)
                    Text(row.humanMsg)
                        .font(PFont.mono(10.5))
                        .foregroundStyle(PColor.fg2)
                        .lineLimit(2)
                        .multilineTextAlignment(.leading)
                }
                Spacer(minLength: 6)
                VStack(alignment: .trailing, spacing: 4) {
                    Chip(text: row.status.rawValue, tone: chipTone(row.status), dot: true)
                    Text(row.trailingTime)
                        .font(PFont.mono(10))
                        .foregroundStyle(PColor.fg3)
                }
            }
            .padding(.vertical, 8).padding(.horizontal, 10)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(isSelected ? PColor.bg4 : Color.clear)
            .overlay(alignment: .leading) {
                if isSelected { Rectangle().fill(PColor.signal).frame(width: 3) }
            }
            .clipShape(RoundedRectangle(cornerRadius: PRadius.sm))
        }
        .buttonStyle(.plain)
        .padding(.horizontal, PSpace.s)
    }

    private func chipTone(_ s: RunEnriched.Status) -> Chip.Tone {
        switch s {
        case .success: return .ok
        case .failed:  return .bad
        case .running: return .signal
        case .aborted: return .warn
        case .skipped: return .neutral
        }
    }
}

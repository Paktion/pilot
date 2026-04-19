import SwiftUI
import AppKit

struct RunDetail: View {
    let item: RunOrLive
    @Binding var diagnoses: [String: (String?, String?)]
    let onCancel: (String) -> Void
    let diagnose: (String) async -> (String?, String?)

    private var isLive: Bool   { if case .live = item { return true } else { return false } }
    private var isFailed: Bool { item.status == .failed }

    private var liveRun: PilotData.LiveRun? {
        if case .live(let l) = item { return l } else { return nil }
    }

    private var pastRun: RunEnriched? {
        if case .past(let r) = item { return r } else { return nil }
    }

    private var stepIdx: Int {
        max(0, (liveRun?.steps.count ?? 1) - 1)
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: PSpace.l) {
                head
                if isLive { liveBand }
                if isFailed { failedBand }
                panes
            }
            .padding(PSpace.xl)
        }
        .task(id: item.rowID) {
            if let r = pastRun, diagnoses[r.id] == nil, r.status == .failed {
                let result = await diagnose(r.id)
                diagnoses[r.id] = result
            }
        }
    }

    private var head: some View {
        HStack(alignment: .top, spacing: 12) {
            AppMark(app: item.workflowApp, size: 32)
            VStack(alignment: .leading, spacing: 2) {
                Text(item.workflowName)
                    .font(PFont.display(14, weight: .semibold))
                    .foregroundStyle(PColor.fg0)
                    .lineLimit(1).truncationMode(.tail)
                Text(headSubtitle)
                    .font(PFont.mono(11))
                    .foregroundStyle(PColor.fg3)
            }
            Spacer()
            HStack(spacing: 6) {
                if let live = liveRun {
                    PButton("Cancel", variant: .danger, size: .small) {
                        onCancel(live.id)
                    }
                }
                if isFailed { PButton("", icon: "arrow.clockwise", variant: .ghost, size: .icon) {} }
                PButton("", icon: "terminal", variant: .ghost, size: .icon) {}
            }
        }
    }

    private var headSubtitle: String {
        if let live = liveRun {
            return "\(live.runID ?? live.id) · started \(formatStart(live.startedAt))"
        }
        if let r = pastRun { return "\(r.id) · \(r.at)" }
        return ""
    }

    private func formatStart(_ d: Date) -> String {
        let f = DateFormatter()
        f.dateFormat = "HH:mm:ss"
        return f.string(from: d)
    }

    private var liveBand: some View {
        HStack(alignment: .center, spacing: 12) {
            HStack(alignment: .center, spacing: 10) {
                StatusDot(tone: .signal, size: 10)
                VStack(alignment: .leading, spacing: 2) {
                    Text("Running · \(item.humanMsg)")
                        .font(PFont.ui(12.5, weight: .medium))
                        .foregroundStyle(PColor.fg0)
                    Text("step \(stepIdx + 1) · elapsed \(liveRun?.elapsed ?? "—")")
                        .font(PFont.mono(11))
                        .foregroundStyle(PColor.fg2)
                }
            }
            Spacer()
            RunProgressBar(width: 180)
        }
        .padding(.horizontal, PSpace.l).padding(.vertical, PSpace.m)
        .background(PColor.signalDim)
        .overlay(RoundedRectangle(cornerRadius: PRadius.md).stroke(PColor.signal.opacity(0.30), lineWidth: 0.5))
        .clipShape(RoundedRectangle(cornerRadius: PRadius.md))
    }

    private var failedBand: some View {
        let cached = pastRun.flatMap { diagnoses[$0.id] }
        let humanMsg = cached?.0 ?? pastRun?.humanMsg ?? item.humanMsg
        return HStack(alignment: .center, spacing: 10) {
            StatusDot(tone: .bad, size: 10)
            VStack(alignment: .leading, spacing: 2) {
                Text(humanMsg)
                    .font(PFont.ui(12.5, weight: .medium))
                    .foregroundStyle(PColor.fg0)
                Text("Failed at \(pastRun?.stepLabel ?? "—") · \(pastRun?.duration ?? "—") · \(String(format: "$%.3f", pastRun?.cost ?? 0))")
                    .font(PFont.ui(12))
                    .foregroundStyle(PColor.fg2)
            }
            Spacer()
        }
        .padding(.horizontal, PSpace.l).padding(.vertical, PSpace.m)
        .background(PColor.bad.opacity(0.12))
        .overlay(RoundedRectangle(cornerRadius: PRadius.md).stroke(PColor.bad.opacity(0.30), lineWidth: 0.5))
        .clipShape(RoundedRectangle(cornerRadius: PRadius.md))
    }

    private var panes: some View {
        HStack(alignment: .top, spacing: PSpace.l) {
            timelinePane.frame(maxWidth: .infinity, alignment: .topLeading)
            shotPane.frame(width: 320)
        }
    }

    @ViewBuilder
    private var timelinePane: some View {
        VStack(alignment: .leading, spacing: PSpace.s) {
            Text("Timeline").kicker()
            VStack(alignment: .leading, spacing: 2) {
                if let live = liveRun {
                    ForEach(Array(live.steps.enumerated()), id: \.offset) { i, s in
                        logRow(t: s.t, kind: s.kind, msg: s.msg, current: i == stepIdx)
                    }
                } else if let r = pastRun {
                    let timeTail = String(r.at.suffix(8))
                    logRow(t: timeTail, kind: .started, msg: "▶ started workflow", current: false)
                    if r.status == .failed {
                        logRow(t: "+02s", kind: .step, msg: "[1] open_app \(r.workflowApp)", current: false)
                        if let label = r.stepLabel {
                            logRow(t: "+08s", kind: .step, msg: "[2] \(label)", current: false)
                        }
                        logRow(t: "+12s", kind: .failed, msg: "✗ \(r.humanMsg)", current: true)
                        if r.rawError != nil { rawErrorDisclosure(r) }
                        suggestionCallout(r)
                    } else {
                        logRow(t: r.duration ?? "+0s", kind: .done, msg: "✓ \(r.humanMsg)", current: false)
                    }
                }
            }
        }
        .padding(PSpace.l)
        .background(PColor.bg2)
        .overlay(RoundedRectangle(cornerRadius: PRadius.lg).stroke(PColor.lineSoft, lineWidth: 0.5))
        .clipShape(RoundedRectangle(cornerRadius: PRadius.lg))
    }

    @ViewBuilder
    private func logRow(t: String, kind: RunEnriched.Step.Kind, msg: String, current: Bool) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Text(t).font(PFont.mono(11)).foregroundStyle(PColor.fg3)
                .frame(width: 64, alignment: .leading)
            Text(msg).font(PFont.mono(12)).foregroundStyle(color(for: kind))
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.horizontal, 8).padding(.vertical, 4)
        .background(current ? PColor.signalDim : Color.clear)
        .clipShape(RoundedRectangle(cornerRadius: PRadius.sm))
    }

    private func color(for kind: RunEnriched.Step.Kind) -> Color {
        switch kind {
        case .started: return PColor.fg0
        case .step:    return PColor.info
        case .shot:    return Color(red: 0.45, green: 0.78, blue: 0.78)
        case .done:    return PColor.ok
        case .failed:  return PColor.bad
        }
    }

    @ViewBuilder
    private func rawErrorDisclosure(_ r: RunEnriched) -> some View {
        DisclosureGroup {
            Text(r.rawError ?? "")
                .font(PFont.mono(11.5)).foregroundStyle(PColor.fg1)
                .padding(10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(PColor.bg0)
                .clipShape(RoundedRectangle(cornerRadius: PRadius.sm))
        } label: {
            Text("Raw error").font(PFont.ui(12, weight: .medium)).foregroundStyle(PColor.fg1)
        }
        .padding(.top, 6).tint(PColor.fg2)
    }

    @ViewBuilder
    private func suggestionCallout(_ r: RunEnriched) -> some View {
        let cached = diagnoses[r.id]
        let suggestion = cached?.1 ?? r.suggestion
        if let suggestion, !suggestion.isEmpty {
            VStack(alignment: .leading, spacing: 6) {
                Text("Claude's suggestion").kicker()
                Text(suggestion)
                    .font(PFont.ui(12.5)).foregroundStyle(PColor.fg0)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(PColor.signalDim)
            .overlay(alignment: .leading) { Rectangle().fill(PColor.signal).frame(width: 2) }
            .clipShape(RoundedRectangle(cornerRadius: PRadius.sm))
            .padding(.top, 8)
        }
    }

    @ViewBuilder
    private var shotPane: some View {
        VStack(alignment: .leading, spacing: PSpace.s) {
            HStack(spacing: 6) {
                Text("Live view").kicker()
                Spacer()
                PButton("", icon: "chevron.left", variant: .ghost, size: .icon) {}
                PButton("", icon: "chevron.right", variant: .ghost, size: .icon) {}
            }
            HStack {
                Spacer()
                if let b64 = liveRun?.lastShotB64, let img = decodeShot(b64) {
                    Image(nsImage: img)
                        .resizable()
                        .interpolation(.medium)
                        .aspectRatio(contentMode: .fit)
                        .frame(maxWidth: 260, maxHeight: 360)
                        .clipShape(RoundedRectangle(cornerRadius: 14))
                } else {
                    PhoneMock(running: isLive)
                }
                Spacer()
            }
            .padding(.vertical, 8)
            scrubber
        }
        .padding(PSpace.l)
        .background(PColor.bg2)
        .overlay(RoundedRectangle(cornerRadius: PRadius.lg).stroke(PColor.lineSoft, lineWidth: 0.5))
        .clipShape(RoundedRectangle(cornerRadius: PRadius.lg))
    }

    private func decodeShot(_ b64: String) -> NSImage? {
        guard let data = Data(base64Encoded: b64) else { return nil }
        return NSImage(data: data)
    }

    private var scrubber: some View {
        VStack(spacing: 6) {
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule().fill(PColor.bg4).frame(height: 4)
                    Capsule().fill(PColor.signal)
                        .frame(width: geo.size.width * (isLive ? 0.48 : 1.0), height: 4)
                    ForEach([0.0, 0.2, 0.35, 0.5, 0.65, 0.8], id: \.self) { p in
                        Rectangle().fill(PColor.fg3).frame(width: 1, height: 8)
                            .offset(x: geo.size.width * CGFloat(p), y: -2)
                    }
                }
                .frame(height: 8)
            }
            .frame(height: 8)
            HStack {
                Text(timeStart).font(PFont.mono(10)).foregroundStyle(PColor.fg3)
                Spacer()
                Text(timeEnd).font(PFont.mono(10)).foregroundStyle(PColor.fg3)
            }
        }
    }

    private var timeStart: String {
        if let r = pastRun {
            let tail = String(r.at.suffix(8))
            return tail.contains(":") ? tail : "00:00"
        }
        if let live = liveRun { return formatStart(live.startedAt) }
        return "00:00"
    }
    private var timeEnd: String {
        liveRun?.elapsed ?? pastRun?.duration ?? pastRun?.elapsed ?? "—"
    }
}

struct RunProgressBar: View {
    let width: CGFloat
    var body: some View {
        TimelineView(.animation) { ctx in
            let phase = ctx.date.timeIntervalSinceReferenceDate
            let pulse = 0.65 + 0.35 * sin(phase * 1.6)
            ZStack(alignment: .leading) {
                Capsule().fill(PColor.bg4)
                Capsule().fill(PColor.signal.opacity(pulse)).frame(width: width * 0.48)
            }
            .frame(width: width, height: 4)
        }
    }
}

struct PhoneMock: View {
    let running: Bool

    var body: some View {
        ZStack(alignment: .top) {
            RoundedRectangle(cornerRadius: 28).fill(Color.black)
                .frame(width: 180, height: 360)
                .overlay(RoundedRectangle(cornerRadius: 28).stroke(Color.white.opacity(0.10), lineWidth: 0.5))
            screen.padding(8).frame(width: 180, height: 360)
            UnevenRoundedRectangle(cornerRadii: .init(topLeading: 0, bottomLeading: 10, bottomTrailing: 10, topTrailing: 0))
                .fill(Color.black).frame(width: 56, height: 16).padding(.top, 6)
        }
        .frame(width: 180, height: 360)
    }

    @ViewBuilder
    private var screen: some View {
        ZStack(alignment: .topLeading) {
            RoundedRectangle(cornerRadius: 22).fill(PColor.bg2)
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Text("8:30").font(PFont.mono(10, weight: .medium)).foregroundStyle(PColor.fg0)
                    Spacer()
                    Text(running ? "● live" : "frame").font(PFont.mono(10)).foregroundStyle(PColor.fg2)
                }
                .padding(.top, 10)
                Text("Waiting for screenshot")
                    .font(PFont.ui(12, weight: .medium))
                    .foregroundStyle(PColor.fg2)
                    .padding(.top, 4)
                Spacer()
            }
            .padding(.horizontal, 12).padding(.bottom, 8)
        }
        .frame(width: 164, height: 344)
        .clipShape(RoundedRectangle(cornerRadius: 22))
    }
}

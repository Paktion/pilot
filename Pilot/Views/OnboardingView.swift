import SwiftUI
import AppKit

struct OnboardingView: View {
    @EnvironmentObject var appState: AppState
    @Binding var isPresented: Bool

    private struct Check: Identifiable {
        let id: String
        let label: String
        let ok: Bool
        let detail: String
        let actionTitle: String?
        let action: (() -> Void)?
    }

    private var checks: [Check] {
        let h = appState.data.health
        let probes = h.probes

        let daemonDetail: String
        if appState.daemonConnected && !h.version.isEmpty && h.version != "—" {
            daemonDetail = "v\(h.version) · PID \(h.pid) · \(h.uptime) uptime"
        } else {
            daemonDetail = "Daemon socket not reachable"
        }

        let keyDetail = h.apiKeyOK ? "Loaded from .env" : "Drop your sk-ant-… into .env"

        return [
            .init(id: "daemon", label: "Daemon connected",
                  ok: appState.daemonConnected,
                  detail: daemonDetail,
                  actionTitle: nil, action: nil),
            .init(id: "key", label: "Anthropic API key",
                  ok: h.apiKeyOK,
                  detail: keyDetail,
                  actionTitle: nil, action: nil),
            .init(id: "ax", label: "Accessibility permission",
                  ok: probes["accessibility"]?.ok ?? false,
                  detail: probes["accessibility"]?.detail.nonEmpty
                          ?? "Needed to simulate taps and swipes",
                  actionTitle: "Open Settings",
                  action: { SettingsDeepLink.open(SettingsDeepLink.accessibility) }),
            .init(id: "sr", label: "Screen Recording permission",
                  ok: probes["screen_recording"]?.ok ?? false,
                  detail: probes["screen_recording"]?.detail.nonEmpty
                          ?? "Needed to read the Mirroring window",
                  actionTitle: "Open Settings",
                  action: { SettingsDeepLink.open(SettingsDeepLink.screenRecording) }),
            .init(id: "mir", label: "iPhone Mirroring app open",
                  ok: probes["iphone_mirroring_window"]?.ok ?? false,
                  detail: probes["iphone_mirroring_window"]?.detail.nonEmpty
                          ?? "Launch iPhone Mirroring on this Mac",
                  actionTitle: "Launch",
                  action: { Self.launchMirroring() }),
        ]
    }

    private static func launchMirroring() {
        let url = URL(fileURLWithPath: "/System/Applications/iPhone Mirroring.app")
        NSWorkspace.shared.open(url)
    }

    private var okCount: Int { checks.filter { $0.ok }.count }
    private var total: Int { checks.count }
    private var allOk: Bool { okCount == total }

    var body: some View {
        ScrollView {
            card
                .padding(.horizontal, 32)
                .padding(.vertical, 28)
                .frame(maxWidth: 760)
                .frame(maxWidth: .infinity)
        }
        .frame(width: 700, height: 640)
        .background(PColor.bg1)
        .task { await appState.data.refreshHealth(deep: true) }
    }

    private var card: some View {
        VStack(alignment: .leading, spacing: PSpace.l) {
            header
            progress
            checklist
            features
            actions
        }
        .padding(28)
        .background(PColor.bg2)
        .overlay(
            RoundedRectangle(cornerRadius: PRadius.xl)
                .stroke(PColor.lineSoft, lineWidth: 0.5)
        )
        .clipShape(RoundedRectangle(cornerRadius: PRadius.xl))
    }

    private var header: some View {
        HStack(alignment: .top, spacing: PSpace.l) {
            mark
            VStack(alignment: .leading, spacing: 6) {
                Text("Welcome to Pilot")
                    .kicker()
                    .foregroundStyle(PColor.signal)
                Text("Let's get your Mac talking to your phone.")
                    .font(PFont.display(26, weight: .semibold))
                    .foregroundStyle(PColor.fg0)
                Text("Pilot records, schedules, and replays iPhone workflows using macOS iPhone Mirroring + Claude. A couple of permissions unlock the whole thing.")
                    .font(PFont.ui(13))
                    .foregroundStyle(PColor.fg2)
                    .lineSpacing(3)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 0)
            PButton("Skip for now", variant: .ghost, size: .small) {
                isPresented = false
            }
        }
    }

    private var mark: some View {
        Image("PilotIcon")
            .resizable()
            .interpolation(.high)
            .frame(width: 48, height: 48)
            .clipShape(RoundedRectangle(cornerRadius: 11))
            .overlay(
                RoundedRectangle(cornerRadius: 11)
                    .stroke(Color.white.opacity(0.10), lineWidth: 0.5)
            )
            .shadow(color: .black.opacity(0.40), radius: 10, x: 0, y: 4)
    }

    private var progress: some View {
        let pct = Double(okCount) / Double(total)
        return HStack(spacing: PSpace.m) {
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 2)
                        .fill(PColor.bg4)
                    RoundedRectangle(cornerRadius: 2)
                        .fill(PColor.signal)
                        .frame(width: geo.size.width * pct)
                }
            }
            .frame(height: 4)
            Text("\(okCount) of \(total) ready")
                .font(PFont.mono(11))
                .foregroundStyle(PColor.fg2)
        }
    }

    private var checklist: some View {
        VStack(spacing: 0) {
            ForEach(Array(checks.enumerated()), id: \.element.id) { idx, c in
                checkRow(c)
                if idx < checks.count - 1 {
                    Rectangle().fill(PColor.lineSoft).frame(height: 0.5)
                }
            }
        }
        .background(PColor.bg2)
        .overlay(
            RoundedRectangle(cornerRadius: PRadius.lg)
                .stroke(PColor.lineSoft, lineWidth: 0.5)
        )
        .clipShape(RoundedRectangle(cornerRadius: PRadius.lg))
    }

    private func checkRow(_ c: Check) -> some View {
        HStack(spacing: PSpace.m) {
            ZStack {
                Circle()
                    .fill(c.ok ? PColor.signalDim : PColor.bad.opacity(0.18))
                    .frame(width: 24, height: 24)
                Image(systemName: c.ok ? "checkmark" : "exclamationmark")
                    .font(.system(size: 11, weight: .bold))
                    .foregroundStyle(c.ok ? PColor.signalInk : PColor.bad)
            }
            VStack(alignment: .leading, spacing: 2) {
                Text(c.label)
                    .font(PFont.ui(13, weight: .medium))
                    .foregroundStyle(PColor.fg0)
                Text(c.detail)
                    .font(PFont.ui(12))
                    .foregroundStyle(PColor.fg2)
            }
            Spacer(minLength: 0)
            if let title = c.actionTitle, let action = c.action {
                PButton(title, icon: "arrow.up.forward.app",
                        variant: .ghost, size: .small, action: action)
            }
        }
        .padding(.horizontal, PSpace.l)
        .padding(.vertical, PSpace.m)
        .background(
            c.ok
            ? AnyView(
                LinearGradient(
                    colors: [PColor.signalDim, .clear],
                    startPoint: .leading, endPoint: .trailing
                )
            )
            : AnyView(Color.clear)
        )
    }

    private var features: some View {
        HStack(spacing: 8) {
            featTile(icon: "square.grid.2x2", label: "Library", sub: "Saved workflows")
            featTile(icon: "sparkles", label: "Author", sub: "English → YAML")
            featTile(icon: "calendar", label: "Schedule", sub: "Cron for iPhone")
            featTile(icon: "dot.radiowaves.left.and.right", label: "Replay", sub: "Frame-by-frame")
        }
    }

    private func featTile(icon: String, label: String, sub: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Image(systemName: icon)
                .font(.system(size: 14, weight: .medium))
                .foregroundStyle(PColor.signal)
                .padding(.bottom, 2)
            Text(label)
                .font(PFont.ui(12.5, weight: .semibold))
                .foregroundStyle(PColor.fg0)
            Text(sub)
                .font(PFont.ui(11.5))
                .foregroundStyle(PColor.fg2)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(PColor.bg1)
        .overlay(
            RoundedRectangle(cornerRadius: PRadius.md)
                .stroke(PColor.lineSoft, lineWidth: 0.5)
        )
        .clipShape(RoundedRectangle(cornerRadius: PRadius.md))
    }

    private var actions: some View {
        VStack(spacing: 0) {
            Rectangle().fill(PColor.lineSoft).frame(height: 0.5)
            HStack {
                Text("Re-open this checklist any time from the status pill in the sidebar.")
                    .font(PFont.ui(12))
                    .foregroundStyle(PColor.fg2)
                Spacer()
                PButton(
                    allOk ? "Get started" : "Grant \(total - okCount) more",
                    icon: allOk ? "chevron.right" : nil,
                    variant: .primary,
                    size: .regular
                ) {
                    isPresented = false
                }
                .disabled(!allOk)
                .opacity(allOk ? 1.0 : 0.5)
            }
            .padding(.top, PSpace.m)
        }
    }
}

private extension String {
    var nonEmpty: String? { isEmpty ? nil : self }
}

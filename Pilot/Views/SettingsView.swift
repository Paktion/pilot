import SwiftUI
import AppKit

struct SettingsView: View {
    @EnvironmentObject var appState: AppState
    @State private var section: String = "health"

    private struct Section: Identifiable {
        let id: String
        let label: String
        let icon: String
    }

    private let sections: [Section] = [
        .init(id: "health",    label: "Health & permissions", icon: "checkmark"),
        .init(id: "budget",    label: "Budget & usage",       icon: "dollarsign.circle"),
        .init(id: "anthropic", label: "Anthropic API",        icon: "key"),
        .init(id: "advanced",  label: "Advanced",             icon: "terminal"),
    ]

    var body: some View {
        HStack(alignment: .top, spacing: 18) {
            nav
                .frame(width: 200)
            ScrollView {
                Group {
                    switch section {
                    case "health":    SettingsHealth()
                    case "budget":    SettingsBudget()
                    case "anthropic": SettingsAnthropic()
                    case "advanced":  SettingsAdvanced()
                    default:          SettingsHealth()
                    }
                }
                .padding(PSpace.xl)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(PColor.bg1)
    }

    private var nav: some View {
        VStack(alignment: .leading, spacing: 4) {
            ForEach(sections) { s in
                Button {
                    section = s.id
                } label: {
                    HStack(spacing: 10) {
                        Image(systemName: s.icon)
                            .font(.system(size: 12, weight: .medium))
                            .foregroundStyle(section == s.id ? PColor.signal : PColor.fg2)
                            .frame(width: 16)
                        Text(s.label)
                            .font(PFont.ui(12.5, weight: .medium))
                            .foregroundStyle(section == s.id ? PColor.fg0 : PColor.fg1)
                        Spacer(minLength: 0)
                    }
                    .padding(.horizontal, PSpace.m)
                    .padding(.vertical, 8)
                    .background(section == s.id ? PColor.bg4 : Color.clear)
                    .overlay(
                        RoundedRectangle(cornerRadius: PRadius.md)
                            .stroke(section == s.id ? PColor.line : .clear, lineWidth: 0.5)
                    )
                    .clipShape(RoundedRectangle(cornerRadius: PRadius.md))
                    .contentShape(RoundedRectangle(cornerRadius: PRadius.md))
                }
                .buttonStyle(.plain)
            }
            Spacer(minLength: 0)
        }
        .padding(.top, PSpace.xl)
        .padding(.leading, PSpace.l)
    }
}

private struct SettingsHealth: View {
    @EnvironmentObject var appState: AppState
    @State private var probing: Bool = false

    private struct PermSpec: Identifiable {
        let id: String
        let name: String
        let probeKey: String
        let fallbackDetail: String
        let action: (() -> Void)?
    }

    private var permSpecs: [PermSpec] {
        [
            .init(id: "ax", name: "Accessibility",
                  probeKey: "accessibility",
                  fallbackDetail: "Needed to simulate taps and swipes",
                  action: { SettingsDeepLink.open(SettingsDeepLink.accessibility) }),
            .init(id: "sr", name: "Screen Recording",
                  probeKey: "screen_recording",
                  fallbackDetail: "Needed to read the Mirroring window",
                  action: { SettingsDeepLink.open(SettingsDeepLink.screenRecording) }),
            .init(id: "mir", name: "iPhone Mirroring window",
                  probeKey: "iphone_mirroring_window",
                  fallbackDetail: "Open iPhone Mirroring on your Mac",
                  action: nil),
            .init(id: "os", name: "macOS version",
                  probeKey: "macos_version",
                  fallbackDetail: "Requires macOS Sequoia 15.0 or later",
                  action: nil),
        ]
    }

    private var badCount: Int {
        let probes = appState.data.health.probes
        return permSpecs.filter { spec in
            if let p = probes[spec.probeKey] { return !p.ok }
            return false
        }.count
    }

    private var allOK: Bool { badCount == 0 && !appState.data.health.probes.isEmpty }

    var body: some View {
        VStack(alignment: .leading, spacing: PSpace.l) {
            if !appState.daemonConnected {
                offlineCard
            }
            heroCard
            permList
            daemonDetails
        }
        .task { await appState.data.refreshHealth(deep: true) }
    }

    private var offlineCard: some View {
        HStack(alignment: .top, spacing: PSpace.m) {
            StatusDot(tone: .bad).padding(.top, 4)
            VStack(alignment: .leading, spacing: 4) {
                Text("Daemon offline")
                    .font(PFont.ui(14, weight: .semibold))
                    .foregroundStyle(PColor.fg0)
                Text(appState.connectStatus.isEmpty
                     ? "Pilot can't reach the Python daemon. Connect to an existing one or start it."
                     : appState.connectStatus)
                    .font(PFont.ui(12.5))
                    .foregroundStyle(PColor.fg2)
            }
            Spacer(minLength: 0)
            if appState.connectAttempting {
                ProgressView().controlSize(.small)
            }
            PButton("Connect", variant: .ghost, size: .small) {
                Task { await appState.tryConnect() }
            }
            .disabled(appState.connectAttempting)
            PButton("Start daemon", variant: .primary, size: .small) {
                Task { await appState.startDaemon() }
            }
            .disabled(appState.connectAttempting)
        }
        .padding(18)
        .background(
            LinearGradient(
                colors: [PColor.bad.opacity(0.12), PColor.bad.opacity(0.04)],
                startPoint: .topLeading, endPoint: .bottomTrailing
            )
        )
        .overlay(alignment: .leading) {
            Rectangle().fill(PColor.bad).frame(width: 2)
        }
        .overlay(
            RoundedRectangle(cornerRadius: PRadius.lg)
                .stroke(PColor.lineSoft, lineWidth: 0.5)
        )
        .clipShape(RoundedRectangle(cornerRadius: PRadius.lg))
    }

    private var heroCard: some View {
        let okHero = allOK
        return HStack(alignment: .top, spacing: PSpace.m) {
            StatusDot(tone: okHero ? .ok : .warn)
                .padding(.top, 4)
            VStack(alignment: .leading, spacing: 2) {
                Text(okHero ? "All systems go"
                            : "\(badCount) permission\(badCount == 1 ? "" : "s") need attention")
                    .font(PFont.ui(14, weight: .semibold))
                    .foregroundStyle(PColor.fg0)
                Text(okHero
                     ? "Daemon is healthy and all probes returned ok."
                     : "Pilot can't run workflows until Accessibility and Screen Recording are granted.")
                    .font(PFont.ui(12.5))
                    .foregroundStyle(PColor.fg2)
            }
            Spacer(minLength: 0)
            if probing {
                ProgressView().controlSize(.small)
            }
            PButton(probing ? "Checking…" : "Run full check",
                    variant: .primary, size: .small) {
                Task {
                    probing = true
                    await appState.data.refreshHealth(deep: true)
                    probing = false
                }
            }
            .disabled(probing)
        }
        .padding(18)
        .background(
            LinearGradient(
                colors: okHero
                    ? [PColor.signalDim, PColor.signal.opacity(0.04)]
                    : [PColor.warn.opacity(0.12), PColor.warn.opacity(0.04)],
                startPoint: .topLeading, endPoint: .bottomTrailing
            )
        )
        .overlay(alignment: .leading) {
            Rectangle().fill(okHero ? PColor.signal : PColor.warn).frame(width: 2)
        }
        .overlay(
            RoundedRectangle(cornerRadius: PRadius.lg)
                .stroke(PColor.lineSoft, lineWidth: 0.5)
        )
        .clipShape(RoundedRectangle(cornerRadius: PRadius.lg))
    }

    private var permList: some View {
        VStack(spacing: 0) {
            ForEach(Array(permSpecs.enumerated()), id: \.element.id) { idx, p in
                permRow(p)
                if idx < permSpecs.count - 1 {
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

    private func permRow(_ p: PermSpec) -> some View {
        let probe = appState.data.health.probes[p.probeKey]
        let isOK = probe?.ok ?? false
        let detail = (probe?.detail.isEmpty == false ? probe!.detail : p.fallbackDetail)
        return HStack(spacing: PSpace.m) {
            ZStack {
                Circle().fill((isOK ? PColor.ok : PColor.bad).opacity(0.18))
                    .frame(width: 24, height: 24)
                Image(systemName: isOK ? "checkmark.circle.fill" : "exclamationmark.circle.fill")
                    .font(.system(size: 14, weight: .medium))
                    .foregroundStyle(isOK ? PColor.ok : PColor.bad)
            }
            VStack(alignment: .leading, spacing: 2) {
                Text(p.name)
                    .font(PFont.ui(13, weight: .medium))
                    .foregroundStyle(PColor.fg0)
                Text(detail)
                    .font(PFont.ui(12))
                    .foregroundStyle(PColor.fg2)
            }
            Spacer(minLength: 0)
            if !isOK, let action = p.action {
                PButton("Open Settings", icon: "arrow.up.forward.app",
                        variant: .ghost, size: .small, action: action)
            }
        }
        .padding(.horizontal, PSpace.l)
        .padding(.vertical, PSpace.m)
    }

    private var daemonDetails: some View {
        let h = appState.data.health
        return DisclosureGroup {
            VStack(spacing: 0) {
                kvLine("Status",   h.status, valueColor: PColor.ok)
                kvLine("Version",  h.version)
                kvLine("PID",      "\(h.pid)")
                kvLine("Uptime",   h.uptime)
                kvLine("Platform", h.platform)
            }
            .padding(.top, PSpace.s)
        } label: {
            Text("Daemon details")
                .font(PFont.ui(12.5, weight: .medium))
                .foregroundStyle(PColor.fg1)
        }
        .padding(PSpace.l)
        .background(PColor.bg2)
        .overlay(
            RoundedRectangle(cornerRadius: PRadius.lg)
                .stroke(PColor.lineSoft, lineWidth: 0.5)
        )
        .clipShape(RoundedRectangle(cornerRadius: PRadius.lg))
    }

    private func kvLine(_ key: String, _ value: String, valueColor: Color = PColor.fg0) -> some View {
        HStack {
            Text(key).font(PFont.ui(12.5)).foregroundStyle(PColor.fg2)
            Spacer()
            Text(value).font(PFont.mono(12.5)).foregroundStyle(valueColor)
        }
        .padding(.vertical, 6)
    }
}


private struct SettingsAnthropic: View {
    @EnvironmentObject var appState: AppState
    private static let consoleURL = URL(string: "https://console.anthropic.com/settings/keys")!

    var body: some View {
        VStack(alignment: .leading, spacing: PSpace.l) {
            heroCard
            kvCard
            Text("Drop the sk-ant-… string after ANTHROPIC_API_KEY= in .env and save — no daemon restart needed.")
                .font(PFont.ui(12.5))
                .foregroundStyle(PColor.fg2)
                .lineSpacing(3)
        }
    }

    private var heroCard: some View {
        let loaded = appState.data.health.apiKeyOK
        return HStack(alignment: .top, spacing: PSpace.m) {
            StatusDot(tone: loaded ? .signal : .warn).padding(.top, 4)
            VStack(alignment: .leading, spacing: 2) {
                Text(loaded ? "API key loaded" : "No API key found")
                    .font(PFont.ui(14, weight: .semibold))
                    .foregroundStyle(PColor.fg0)
                HStack(spacing: 4) {
                    if loaded {
                        Text("From")
                            .font(PFont.ui(12.5))
                            .foregroundStyle(PColor.fg2)
                        Text("$ANTHROPIC_API_KEY")
                            .font(PFont.mono(12))
                            .foregroundStyle(PColor.fg2)
                        Text("— lives in .env at the repo root.")
                            .font(PFont.ui(12.5))
                            .foregroundStyle(PColor.fg2)
                    } else {
                        Text("Drop your sk-ant-… into .env")
                            .font(PFont.ui(12.5))
                            .foregroundStyle(PColor.fg2)
                    }
                }
            }
            Spacer(minLength: 0)
            PButton(loaded ? "Rotate key" : "Get key",
                    variant: .ghost, size: .small) {
                NSWorkspace.shared.open(Self.consoleURL)
            }
        }
        .padding(18)
        .background(
            LinearGradient(
                colors: loaded
                    ? [PColor.signalDim, PColor.signal.opacity(0.04)]
                    : [PColor.warn.opacity(0.12), PColor.warn.opacity(0.04)],
                startPoint: .topLeading, endPoint: .bottomTrailing
            )
        )
        .overlay(alignment: .leading) {
            Rectangle().fill(loaded ? PColor.signal : PColor.warn).frame(width: 2)
        }
        .overlay(
            RoundedRectangle(cornerRadius: PRadius.lg)
                .stroke(PColor.lineSoft, lineWidth: 0.5)
        )
        .clipShape(RoundedRectangle(cornerRadius: PRadius.lg))
    }

    private var kvCard: some View {
        SetKVCard {
            SetKVLine(key: "Key",
                      value: appState.data.health.apiKeyOK ? "sk-ant-…(loaded)" : "(not set)",
                      dim: true)
            SetDivider()
            SetKVLine(key: "Model", value: "claude-sonnet-4-5")
            SetDivider()
            SetKVLine(key: "Last validated",
                      value: appState.data.health.apiKeyOK ? "now" : "—",
                      dim: true)
        }
    }
}

private struct SettingsAdvanced: View {
    @EnvironmentObject var appState: AppState
    @State private var pingHint: String? = nil
    @State private var pinging: Bool = false
    @State private var showResetConfirm: Bool = false
    @State private var resetting: Bool = false

    var body: some View {
        VStack(alignment: .leading, spacing: PSpace.l) {
            kvCard
            HStack(spacing: 8) {
                PButton(pinging ? "Pinging…" : "Ping daemon",
                        icon: "bolt", variant: .ghost, size: .small) {
                    Task { await pingDaemon() }
                }
                .disabled(pinging)
                PButton("Open daemon logs", icon: "terminal",
                        variant: .ghost, size: .small) {
                    NSWorkspace.shared.open(URL(fileURLWithPath: "/tmp/pilotd.out"))
                }
                PButton(resetting ? "Resetting…" : "Reset all workflows",
                        variant: .danger, size: .small) {
                    showResetConfirm = true
                }
                .disabled(resetting)
                if let pingHint {
                    Chip(text: pingHint, tone: .ok, dot: true)
                }
            }
        }
        .confirmationDialog("Delete all workflows?",
                            isPresented: $showResetConfirm,
                            titleVisibility: .visible) {
            Button("Delete \(appState.data.workflows.count) workflows", role: .destructive) {
                Task { await resetAll() }
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("This removes every workflow from the daemon's library. Schedules will stop firing.")
        }
    }

    private var kvCard: some View {
        SetKVCard {
            SetKVLine(key: "Session storage",
                      value: "~/Library/Application Support/Pilot/sessions/",
                      dim: true)
            SetDivider()
            SetKVLine(key: "Log level", value: "info")
            SetDivider()
            SetKVLine(key: "Start daemon at login", value: "On", mono: false)
        }
    }

    private func pingDaemon() async {
        pinging = true
        defer { pinging = false }
        await appState.data.refreshHealth()
        pingHint = "Pinged · uptime \(appState.data.health.uptime)"
        try? await Task.sleep(nanoseconds: 2_500_000_000)
        pingHint = nil
    }

    private func resetAll() async {
        resetting = true
        defer { resetting = false }
        for wf in appState.data.workflows {
            _ = try? await appState.client.callOnce(method: "workflow.delete",
                                                    params: ["name": wf.name])
        }
        appState.workflowsVersion += 1
        await appState.data.refreshWorkflows()
    }
}

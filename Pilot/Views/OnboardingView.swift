import SwiftUI

/// First-run wizard. Shown when daemon reports ``anthropic_api_key_set=false``
/// or permissions are missing. Four steps: Welcome → Key → Permissions → Done.
struct OnboardingView: View {
    @EnvironmentObject var appState: AppState
    @Binding var isPresented: Bool

    @State private var step: Step = .welcome
    @State private var systemCheck: [String: Any] = [:]
    @State private var isProbing = false

    enum Step: Int, CaseIterable, Identifiable {
        case welcome, key, permissions, ready
        var id: Int { rawValue }
        var title: String {
            switch self {
            case .welcome:     return "Welcome"
            case .key:         return "API Key"
            case .permissions: return "Permissions"
            case .ready:       return "Ready"
            }
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()
            content
                .padding(24)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            Divider()
            footer
        }
        .frame(width: 620, height: 480)
        .task { await refreshChecks() }
    }

    private var header: some View {
        VStack(spacing: 8) {
            HStack(spacing: 24) {
                ForEach(Step.allCases) { s in
                    VStack(spacing: 4) {
                        Circle()
                            .fill(s.rawValue <= step.rawValue ? Color.accentColor : Color.secondary.opacity(0.25))
                            .frame(width: 10, height: 10)
                        Text(s.title).font(.caption2)
                            .foregroundStyle(s.rawValue <= step.rawValue ? .primary : .secondary)
                    }
                }
            }
        }
        .padding(.vertical, 14)
    }

    @ViewBuilder
    private var content: some View {
        switch step {
        case .welcome:     welcomeView
        case .key:         keyView
        case .permissions: permissionsView
        case .ready:       readyView
        }
    }

    private var footer: some View {
        HStack {
            Button("Skip") { isPresented = false }
            Spacer()
            if step != .welcome {
                Button("Back") { step = Step(rawValue: step.rawValue - 1) ?? .welcome }
            }
            if step == .ready {
                Button("Get started") { isPresented = false }
                    .buttonStyle(.borderedProminent)
                    .keyboardShortcut(.defaultAction)
            } else {
                Button("Continue") { advance() }
                    .buttonStyle(.borderedProminent)
                    .keyboardShortcut(.defaultAction)
            }
        }
        .padding()
    }

    private var welcomeView: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Meet Pilot").font(.largeTitle).bold()
            Text("Pilot records, schedules, and replays iPhone workflows using macOS iPhone Mirroring + Claude.")
                .foregroundStyle(.secondary)
            VStack(alignment: .leading, spacing: 8) {
                feature("square.grid.2x2", "Library of workflows")
                feature("wand.and.stars", "Natural-language drafting")
                feature("calendar.badge.clock", "Scheduled runs")
                feature("dot.radiowaves.up.forward", "Live event streaming")
            }
            .padding(.top, 4)
        }
    }

    private var keyView: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Add your Anthropic API key").font(.title2).bold()
            Text("Pilot uses Claude for drafting, planning, and reasoning about the phone screen. The key lives locally in `.env` — never committed.")
                .foregroundStyle(.secondary)
            HStack {
                Circle().fill(keyPresent ? .green : .red).frame(width: 10, height: 10)
                Text(keyPresent ? "Key detected" : "No key yet")
            }
            if !keyPresent {
                Text("Open `/Users/sohumsuthar/Documents/GitHub/pilot-workspace/pilot/.env` and replace `sk-ant-REPLACE-ME` with your key.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
                HStack {
                    Button("Open Anthropic Console") {
                        SettingsDeepLink.open(URL(string: "https://console.anthropic.com/settings/keys")!)
                    }
                    Button("Recheck") { Task { await refreshChecks() } }
                }
            }
        }
    }

    private var permissionsView: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Grant macOS permissions").font(.title2).bold()
            Text("Pilot needs Accessibility (to simulate taps) and Screen Recording (to capture the Mirroring window).")
                .foregroundStyle(.secondary)

            permissionRow(
                label: "Accessibility",
                ok: checkOk("accessibility"),
                action: { SettingsDeepLink.open(SettingsDeepLink.accessibility) }
            )
            permissionRow(
                label: "Screen Recording",
                ok: checkOk("screen_recording"),
                action: { SettingsDeepLink.open(SettingsDeepLink.screenRecording) }
            )
            permissionRow(
                label: "iPhone Mirroring running",
                ok: checkOk("iphone_mirroring_window"),
                action: nil
            )

            if isProbing {
                HStack { ProgressView().controlSize(.small); Text("Checking…") }
            }
            Button("Re-check permissions") { Task { await refreshChecks() } }
                .controlSize(.small)
        }
    }

    private var readyView: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("You're set").font(.largeTitle).bold()
            Text("The daemon is running and 4 workflows are pre-seeded. Try drafting your own in the Author tab.")
                .foregroundStyle(.secondary)
            VStack(alignment: .leading, spacing: 6) {
                checklist("Daemon connected", appState.client.isConnected)
                checklist("Anthropic key", keyPresent)
                checklist("Accessibility", checkOk("accessibility"))
                checklist("Screen Recording", checkOk("screen_recording"))
            }
            .padding(.top, 4)
        }
    }

    // MARK: - Helpers

    private var keyPresent: Bool {
        (systemCheck["api_key"] as? Bool) == true
    }

    private func checkOk(_ key: String) -> Bool {
        if let tuple = systemCheck[key] as? [Any], let ok = tuple.first as? Bool { return ok }
        if let b = systemCheck[key] as? Bool { return b }
        return false
    }

    private func feature(_ icon: String, _ text: String) -> some View {
        HStack {
            Image(systemName: icon).frame(width: 22)
            Text(text)
        }
    }

    private func permissionRow(label: String, ok: Bool, action: (() -> Void)?) -> some View {
        HStack {
            Image(systemName: ok ? "checkmark.circle.fill" : "xmark.circle.fill")
                .foregroundStyle(ok ? .green : .red)
            Text(label)
            Spacer()
            if !ok, let action {
                Button("Open Settings", action: action).controlSize(.small)
            }
        }
    }

    private func checklist(_ text: String, _ ok: Bool) -> some View {
        HStack {
            Image(systemName: ok ? "checkmark.circle.fill" : "circle")
                .foregroundStyle(ok ? .green : .secondary)
            Text(text).foregroundStyle(ok ? .primary : .secondary)
        }
    }

    private func advance() {
        let next = Step(rawValue: step.rawValue + 1) ?? .ready
        step = next
        Task { await refreshChecks() }
    }

    private func refreshChecks() async {
        isProbing = true
        defer { isProbing = false }
        if !appState.client.isConnected { await appState.client.connect() }
        if let r = try? await appState.client.callOnce(method: "health.full_check") {
            self.systemCheck = r
        }
    }
}

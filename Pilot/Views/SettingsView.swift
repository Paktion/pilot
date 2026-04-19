import SwiftUI
#if canImport(AppKit)
import AppKit
#endif

struct SettingsView: View {
    @EnvironmentObject var appState: AppState
    @State private var health: [String: Any] = [:]
    @State private var usage: [String: Any] = [:]
    @State private var systemCheck: [String: Any] = [:]
    @State private var isLoading = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Text("Settings").font(.title2).bold()

                daemonSection
                permissionsSection
                anthropicSection
                budgetSection
                actionsSection

                Spacer(minLength: 20)
            }
            .padding()
        }
        .task { await reload() }
    }

    // MARK: - Sections

    private var daemonSection: some View {
        GroupBox("Daemon") {
            VStack(alignment: .leading, spacing: 4) {
                RowView(label: "Status", value: health["status"] as? String ?? "—")
                RowView(label: "Version", value: health["version"] as? String ?? "—")
                RowView(label: "PID", value: "\(health["pid"] as? Int ?? 0)")
                RowView(label: "Uptime", value: uptimeLabel)
                RowView(label: "Platform", value: health["platform"] as? String ?? "—")
            }
            .padding(6)
        }
    }

    private var permissionsSection: some View {
        GroupBox("macOS permissions") {
            VStack(alignment: .leading, spacing: 6) {
                PermissionRow(
                    label: "Accessibility",
                    ok: permissionOk("accessibility"),
                    detail: permissionDetail("accessibility"),
                    action: {
                        SettingsDeepLink.open(SettingsDeepLink.accessibility)
                    }
                )
                PermissionRow(
                    label: "Screen Recording",
                    ok: permissionOk("screen_recording"),
                    detail: permissionDetail("screen_recording"),
                    action: {
                        SettingsDeepLink.open(SettingsDeepLink.screenRecording)
                    }
                )
                PermissionRow(
                    label: "iPhone Mirroring window",
                    ok: (systemCheck["iphone_mirroring_window"] as? [Any])?.first as? Bool ?? false,
                    detail: permissionDetail("iphone_mirroring_window"),
                    action: nil
                )
                PermissionRow(
                    label: "macOS version",
                    ok: (systemCheck["macos_version"] as? [Any])?.first as? Bool ?? false,
                    detail: permissionDetail("macos_version"),
                    action: nil
                )
            }
            .padding(6)
        }
    }

    private var anthropicSection: some View {
        GroupBox("Anthropic API") {
            VStack(alignment: .leading, spacing: 6) {
                HStack {
                    Circle().fill(keyPresent ? .green : .red).frame(width: 8, height: 8)
                    Text(keyPresent ? "API key loaded from $ANTHROPIC_API_KEY" : "No API key")
                        .font(.callout)
                    Spacer()
                    if !keyPresent {
                        Button("Get key") {
                            SettingsDeepLink.open(URL(string: "https://console.anthropic.com/settings/keys")!)
                        }
                        .controlSize(.small)
                    }
                }
                Text("The key lives in .env (gitignored). Drop the `sk-ant-…` string into /Users/sohumsuthar/Documents/GitHub/pilot-workspace/pilot/.env — no restart needed.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .padding(6)
        }
    }

    private var budgetSection: some View {
        GroupBox("Budget") {
            VStack(alignment: .leading, spacing: 4) {
                BudgetBar(
                    label: "Today",
                    spent: usage["daily_cost"] as? Double ?? 0,
                    cap: usage["daily_budget"] as? Double ?? 0
                )
                BudgetBar(
                    label: "This month",
                    spent: usage["monthly_cost"] as? Double ?? 0,
                    cap: usage["monthly_budget"] as? Double ?? 0
                )
                RowView(label: "Total calls", value: "\(usage["total_calls"] as? Int ?? 0)")
                RowView(label: "Per-task cap", value: String(format: "$%.2f", usage["per_task_budget"] as? Double ?? 0))
            }
            .padding(6)
        }
    }

    private var actionsSection: some View {
        GroupBox("Debug") {
            HStack {
                Button("Ping daemon") { Task { await reload() } }
                Button("Run full system check") { Task { await fullCheck() } }
                if isLoading { ProgressView().controlSize(.small) }
            }
            .padding(6)
        }
    }

    // MARK: - Helpers

    private var keyPresent: Bool { health["anthropic_api_key_set"] as? Bool ?? false }

    private var uptimeLabel: String {
        guard let s = health["uptime_s"] as? Double else { return "—" }
        if s < 60 { return String(format: "%.0f s", s) }
        if s < 3600 { return String(format: "%.0f m", s / 60) }
        return String(format: "%.1f h", s / 3600)
    }

    private func permissionOk(_ key: String) -> Bool {
        if let tuple = systemCheck[key] as? [Any], let ok = tuple.first as? Bool { return ok }
        return false
    }

    private func permissionDetail(_ key: String) -> String {
        if let tuple = systemCheck[key] as? [Any], tuple.count >= 2,
           let desc = tuple[1] as? String { return desc }
        return ""
    }

    private func reload() async {
        if !appState.client.isConnected { await appState.client.connect() }
        if let r = try? await appState.client.callOnce(method: "health.check") {
            self.health = r
        }
        if let r = try? await appState.client.callOnce(method: "usage.summary") {
            self.usage = r
        }
    }

    private func fullCheck() async {
        isLoading = true
        defer { isLoading = false }
        if !appState.client.isConnected { await appState.client.connect() }
        if let r = try? await appState.client.callOnce(method: "health.full_check") {
            self.systemCheck = r
        }
    }
}

// MARK: - Small components

private struct RowView: View {
    let label: String
    let value: String
    var body: some View {
        HStack {
            Text(label).foregroundStyle(.secondary)
            Spacer()
            Text(value).font(.callout.monospaced())
        }
    }
}

private struct PermissionRow: View {
    let label: String
    let ok: Bool
    let detail: String
    let action: (() -> Void)?

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack {
                Image(systemName: ok ? "checkmark.circle.fill" : "xmark.circle.fill")
                    .foregroundStyle(ok ? .green : .red)
                Text(label)
                Spacer()
                if !ok, let action {
                    Button("Open Settings", action: action).controlSize(.small)
                }
            }
            if !detail.isEmpty {
                Text(detail).font(.caption2).foregroundStyle(.tertiary).lineLimit(2)
            }
        }
    }
}

private struct BudgetBar: View {
    let label: String
    let spent: Double
    let cap: Double

    private var pct: Double { cap > 0 ? min(1.0, spent / cap) : 0 }
    private var barColor: Color {
        if pct >= 1.0 { return .red }
        if pct >= 0.8 { return .orange }
        return .green
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack {
                Text(label).foregroundStyle(.secondary)
                Spacer()
                Text(String(format: "$%.3f / $%.2f", spent, cap))
                    .font(.callout.monospaced())
                    .foregroundStyle(pct >= 0.8 ? .red : .primary)
            }
            ProgressView(value: pct).tint(barColor)
        }
    }
}

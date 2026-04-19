import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var appState: AppState

    var body: some View {
        Form {
            Section("Daemon") {
                LabeledContent("Connected", value: appState.daemonConnected ? "yes" : "no")
                LabeledContent("Version", value: appState.daemonVersion.isEmpty ? "—" : appState.daemonVersion)
            }
            Section("Anthropic") {
                Text("API key loaded from $ANTHROPIC_API_KEY in .env (not stored in the app)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Section("Debug") {
                Button("Ping daemon (health.check)") {
                    Task { await appState.client.healthCheck() }
                }
            }
        }
        .formStyle(.grouped)
    }
}

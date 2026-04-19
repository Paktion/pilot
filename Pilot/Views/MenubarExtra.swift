import SwiftUI
import AppKit

struct MenubarContent: View {
    @EnvironmentObject var appState: AppState
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Circle()
                    .fill(appState.daemonConnected ? .green : .red)
                    .frame(width: 8, height: 8)
                Text(appState.daemonConnected ? "Daemon connected" : "Daemon offline")
                    .font(.caption)
            }
            Divider()
            Button("Open Pilot") { openWindow(id: "pilot-main") }
            Button("Quit") { NSApplication.shared.terminate(nil) }
        }
        .padding()
        .frame(width: 220)
    }
}

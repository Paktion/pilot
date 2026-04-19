import SwiftUI

@main
struct PilotApp: App {
    @StateObject private var appState = AppState()

    var body: some Scene {
        // WindowGroup MUST come first — SwiftUI uses the primary scene to
        // decide activation behavior on launch.
        WindowGroup("Pilot", id: "pilot-main") {
            MainWindow()
                .environmentObject(appState)
                .frame(minWidth: 900, minHeight: 600)
        }
        .defaultSize(width: 1100, height: 720)

        MenuBarExtra("Pilot", systemImage: "dot.radiowaves.up.forward") {
            MenubarContent()
                .environmentObject(appState)
        }
        .menuBarExtraStyle(.window)
    }
}

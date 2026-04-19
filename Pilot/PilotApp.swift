import SwiftUI

@main
struct PilotApp: App {
    @StateObject private var appState = AppState()

    var body: some Scene {
        MenuBarExtra("Pilot", systemImage: "dot.radiowaves.up.forward") {
            MenubarContent()
                .environmentObject(appState)
        }
        .menuBarExtraStyle(.window)

        Window("Pilot", id: "pilot-main") {
            MainWindow()
                .environmentObject(appState)
                .frame(minWidth: 900, minHeight: 600)
        }
        .windowResizability(.contentSize)
    }
}

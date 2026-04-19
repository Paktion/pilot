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
                .frame(minWidth: 1100, minHeight: 720)
        }
        .defaultSize(width: 1180, height: 760)

        MenuBarExtra("Pilot", image: "PilotMark") {
            MenubarContent()
                .environmentObject(appState)
        }
        .menuBarExtraStyle(.window)
    }
}

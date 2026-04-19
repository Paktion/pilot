import SwiftUI

struct MainWindow: View {
    enum Tab: String, CaseIterable, Identifiable {
        case library, author, schedule, history, settings
        var id: Self { self }
        var title: String { rawValue.capitalized }
    }

    @State private var selected: Tab = .library

    var body: some View {
        TabView(selection: $selected) {
            LibraryView().tabItem { Label("Library", systemImage: "square.grid.2x2") }.tag(Tab.library)
            AuthoringView().tabItem { Label("Author", systemImage: "wand.and.stars") }.tag(Tab.author)
            ScheduleView().tabItem { Label("Schedule", systemImage: "calendar") }.tag(Tab.schedule)
            HistoryView().tabItem { Label("History", systemImage: "clock") }.tag(Tab.history)
            SettingsView().tabItem { Label("Settings", systemImage: "gearshape") }.tag(Tab.settings)
        }
        .padding()
    }
}

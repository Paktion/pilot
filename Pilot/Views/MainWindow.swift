import SwiftUI

struct MainWindow: View {
    enum Tab: String, CaseIterable, Identifiable {
        case library, author, schedule, history, settings
        var id: Self { self }
        var title: String { rawValue.capitalized }
    }

    @EnvironmentObject var appState: AppState
    @State private var selected: Tab = .library

    var body: some View {
        VStack(spacing: 0) {
            costBar
            Divider()
            TabView(selection: $selected) {
                LibraryView().tabItem { Label("Library", systemImage: "square.grid.2x2") }.tag(Tab.library)
                AuthoringView().tabItem { Label("Author", systemImage: "wand.and.stars") }.tag(Tab.author)
                ScheduleView().tabItem { Label("Schedule", systemImage: "calendar") }.tag(Tab.schedule)
                HistoryView().tabItem { Label("History", systemImage: "clock") }.tag(Tab.history)
                SettingsView().tabItem { Label("Settings", systemImage: "gearshape") }.tag(Tab.settings)
            }
            .padding(.horizontal, 12)
        }
        .onAppear { appState.startCostRefresh() }
        .sheet(isPresented: $appState.showOnboarding) {
            OnboardingView(isPresented: $appState.showOnboarding)
                .environmentObject(appState)
        }
    }

    private var costBar: some View {
        HStack(spacing: 10) {
            Circle()
                .fill(appState.daemonConnected ? .green : .red)
                .frame(width: 8, height: 8)
            Text(appState.daemonConnected ? "daemon connected" : "daemon offline")
                .font(.caption)
                .foregroundStyle(.secondary)
            Spacer()
            HStack(spacing: 4) {
                Image(systemName: "dollarsign.circle")
                    .font(.caption)
                Text(String(format: "%.3f", appState.dailyCost))
                    .font(.caption.monospaced())
                Text("/ \(String(format: "%.2f", appState.dailyBudget)) today")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .foregroundStyle(costColor)
            Button {
                appState.showOnboarding = true
            } label: {
                Label("First-run", systemImage: "sparkles")
            }
            .controlSize(.mini)
            .buttonStyle(.borderless)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 6)
    }

    private var costColor: Color {
        let pct = appState.dailyBudget > 0
            ? appState.dailyCost / appState.dailyBudget : 0
        if pct >= 1.0 { return .red }
        if pct >= 0.8 { return .orange }
        return .primary
    }
}

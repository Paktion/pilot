import SwiftUI

// Top-level window shell for the revamped app.
// Replaces the old TabView layout with a left sidebar + main column.
// The cost bar that used to live above the tabs is now folded into the
// sidebar footer (status pill + budget bars), reclaiming the top 40px.

struct MainWindow: View {
    enum Nav: String, CaseIterable, Identifiable {
        case home, workflows, author, runs, settings
        var id: Self { self }
        var label: String { rawValue.capitalized }
        var systemImage: String {
            switch self {
            case .home:      return "house"
            case .workflows: return "square.grid.2x2"
            case .author:    return "wand.and.stars"
            case .runs:      return "dot.radiowaves.left.and.right"
            case .settings:  return "gearshape"
            }
        }
        var kbd: String? {
            switch self {
            case .home:      return "⌘1"
            case .workflows: return "⌘2"
            case .author:    return "⌘N"
            case .runs:      return "⌘3"
            case .settings:  return "⌘,"
            }
        }
        @MainActor
        func badge(in data: PilotData) -> String? {
            switch self {
            case .workflows:
                let n = data.workflows.count
                return n > 0 ? "\(n)" : nil
            case .runs:
                let n = data.liveRuns.count
                    + data.runs.filter { $0.status == .failed }.count
                return n > 0 ? "\(n)" : nil
            default: return nil
            }
        }
    }

    @EnvironmentObject var appState: AppState
    @State private var nav: Nav = .home
    @State private var openDrawer: WorkflowEnriched? = nil

    var body: some View {
        HStack(spacing: 0) {
            Sidebar(active: $nav)
                .frame(width: 220)
                .environmentObject(appState)
            mainColumn
        }
        .frame(minWidth: 1100, minHeight: 720)
        .background(PColor.bg1)
        .preferredColorScheme(.dark)
        .onAppear { appState.startCostRefresh() }
        .sheet(isPresented: $appState.showOnboarding) {
            OnboardingView(isPresented: $appState.showOnboarding)
                .environmentObject(appState)
        }
        // Workflow detail drawer slides over the main column, scrim included.
        .overlay(alignment: .trailing) {
            if let wf = openDrawer {
                WorkflowDrawerView(workflow: wf, onClose: { openDrawer = nil })
                    .environmentObject(appState)
                    .transition(.move(edge: .trailing).combined(with: .opacity))
                    .zIndex(20)
            }
        }
        .overlay {
            if openDrawer != nil {
                Color.black.opacity(0.4)
                    .ignoresSafeArea()
                    .onTapGesture { openDrawer = nil }
                    .zIndex(10)
                    .transition(.opacity)
            }
        }
        .animation(.easeOut(duration: 0.2), value: openDrawer)
    }

    @ViewBuilder
    private var mainColumn: some View {
        VStack(spacing: 0) {
            MainHeader(nav: nav)
            Divider().background(PColor.lineSoft)
            content
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(PColor.bg1)
        }
    }

    @ViewBuilder
    private var content: some View {
        switch nav {
        case .home:
            HomeView(navigateTo: { nav = $0 },
                     openDrawer: { openDrawer = $0 },
                     onRunStarted: { nav = .runs })
        case .workflows:
            WorkflowsView(openDrawer: { openDrawer = $0 },
                          onAuthor: { nav = .author },
                          onRunStarted: { nav = .runs })
        case .author:
            AuthorView()
        case .runs:
            RunsView()
        case .settings:
            SettingsView()
        }
    }
}

// ─── Sidebar ─────────────────────────────────────────────────────
struct Sidebar: View {
    @EnvironmentObject var appState: AppState
    @Binding var active: MainWindow.Nav

    var body: some View {
        VStack(spacing: 0) {
            // Brand row (traffic lights are owned by the system window chrome on
            // the left edge — we deliberately do NOT draw fake ones here).
            HStack(spacing: 10) {
                BrandMark(size: 22)
                Text("Pilot")
                    .font(PFont.display(14, weight: .semibold))
                    .kerning(-0.2)
                    .foregroundStyle(PColor.fg0)
                Spacer()
                Text("0.2")
                    .font(PFont.mono(10))
                    .foregroundStyle(PColor.fg3)
            }
            .padding(.horizontal, 14)
            .padding(.top, 14)
            .padding(.bottom, 14)

            Divider().background(PColor.lineSoft)

            Text("Workspace").kicker()
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, 12)
                .padding(.top, 12)
                .padding(.bottom, 4)

            ForEach(MainWindow.Nav.allCases) { item in
                NavItem(item: item,
                        active: active == item,
                        badge: item.badge(in: appState.data)) { active = item }
            }

            Spacer()

            VStack(spacing: 10) {
                StatusPill()
                BudgetRow(label: "Today",
                          spent: appState.data.usage.dailyCost,
                          cap: appState.data.usage.dailyBudget,
                          tint: PColor.signal)
                BudgetRow(label: "Month",
                          spent: appState.data.usage.monthlyCost,
                          cap: appState.data.usage.monthlyBudget,
                          tint: Color(red: 0.50, green: 0.50, blue: 0.45))
            }
            .padding(12)
            .overlay(alignment: .top) {
                Rectangle().fill(PColor.lineSoft).frame(height: 0.5)
            }
        }
        .background(PColor.bg2)
        .overlay(alignment: .trailing) {
            Rectangle().fill(PColor.lineSoft).frame(width: 0.5)
        }
    }
}

private struct NavItem: View {
    let item: MainWindow.Nav
    let active: Bool
    let badge: String?
    let action: () -> Void

    @State private var hovering = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: 10) {
                Image(systemName: item.systemImage)
                    .font(.system(size: 13, weight: .regular))
                    .foregroundStyle(active ? PColor.signal : PColor.fg2)
                    .frame(width: 16, height: 16)
                Text(item.label)
                    .font(PFont.ui(13, weight: .medium))
                    .foregroundStyle(active ? PColor.fg0 : PColor.fg1)
                Spacer()
                if let badge {
                    Text(badge)
                        .font(PFont.mono(10))
                        .foregroundStyle(PColor.fg2)
                } else if let kbd = item.kbd {
                    Text(kbd)
                        .font(PFont.mono(10))
                        .foregroundStyle(PColor.fg3)
                        .padding(.horizontal, 5)
                        .padding(.vertical, 1)
                        .overlay(
                            RoundedRectangle(cornerRadius: 4)
                                .stroke(PColor.line, lineWidth: 0.5)
                        )
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(rowBg)
            .clipShape(RoundedRectangle(cornerRadius: PRadius.sm))
            .overlay(
                RoundedRectangle(cornerRadius: PRadius.sm)
                    .stroke(active ? PColor.line : .clear, lineWidth: 0.5)
            )
        }
        .buttonStyle(.plain)
        .padding(.horizontal, 8)
        .onHover { hovering = $0 }
    }

    private var rowBg: Color {
        if active   { return PColor.bg4 }
        if hovering { return PColor.bg3 }
        return .clear
    }
}

private struct BrandMark: View {
    let size: CGFloat
    var body: some View {
        Image("PilotIcon")
            .resizable()
            .interpolation(.high)
            .frame(width: size, height: size)
            .clipShape(RoundedRectangle(cornerRadius: size * 0.225))
            .overlay(
                RoundedRectangle(cornerRadius: size * 0.225)
                    .stroke(Color.white.opacity(0.10), lineWidth: 0.5)
            )
            .shadow(color: .black.opacity(0.35), radius: 4, y: 1)
    }
}

struct StatusPill: View {
    @EnvironmentObject var appState: AppState
    var body: some View {
        Menu {
            if appState.daemonConnected {
                Button("Ping daemon") {
                    Task { await appState.data.refreshHealth() }
                }
                Button("Open daemon logs") {
                    NSWorkspace.shared.open(URL(fileURLWithPath: "/tmp/pilotd.out"))
                }
                Divider()
                Button("Disconnect", role: .destructive) {
                    appState.client.disconnect()
                }
            } else {
                Button("Connect") { Task { await appState.tryConnect() } }
                Button("Start daemon") { Task { await appState.startDaemon() } }
                Divider()
                Button("Open daemon logs") {
                    NSWorkspace.shared.open(URL(fileURLWithPath: "/tmp/pilotd.out"))
                }
            }
        } label: {
            HStack(spacing: 8) {
                Circle()
                    .fill(appState.daemonConnected ? PColor.signal : PColor.bad)
                    .frame(width: 6, height: 6)
                    .overlay(
                        Circle()
                            .stroke(appState.daemonConnected
                                    ? PColor.signal.opacity(0.18)
                                    : PColor.bad.opacity(0.18),
                                    lineWidth: 3)
                    )
                Text(appState.daemonConnected ? "Daemon" : "Offline")
                    .font(PFont.ui(11.5, weight: .medium))
                    .foregroundStyle(PColor.fg0)
                Spacer(minLength: 4)
                if appState.connectAttempting {
                    ProgressView()
                        .controlSize(.mini)
                } else if appState.daemonConnected {
                    Text(daemonSubLabel)
                        .font(PFont.mono(10))
                        .foregroundStyle(PColor.fg3)
                        .lineLimit(1)
                } else {
                    Image(systemName: "chevron.up.chevron.down")
                        .font(.system(size: 9, weight: .medium))
                        .foregroundStyle(PColor.fg3)
                }
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 8)
            .background(PColor.bg3)
            .clipShape(RoundedRectangle(cornerRadius: PRadius.sm))
        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
        .help(appState.daemonConnected
              ? "Daemon connected — click for actions"
              : "Daemon offline — click to connect or start it")
    }

    private var daemonSubLabel: String {
        let h = appState.data.health
        if h.pid > 0 { return "PID \(h.pid) · \(h.uptime)" }
        return h.uptime
    }
}

struct BudgetRow: View {
    let label: String
    let spent: Double
    let cap: Double
    let tint: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(label)
                    .font(PFont.mono(10.5))
                    .foregroundStyle(PColor.fg2)
                Spacer()
                Text(String(format: "$%.3f / $%.2f", spent, cap))
                    .font(PFont.mono(10.5, weight: .medium))
                    .foregroundStyle(PColor.fg0)
            }
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule()
                        .fill(PColor.bg4)
                        .frame(height: 3)
                    Capsule()
                        .fill(tint)
                        .frame(width: geo.size.width * pct, height: 3)
                }
            }
            .frame(height: 3)
        }
        .padding(.horizontal, 2)
    }

    private var pct: CGFloat {
        guard cap > 0 else { return 0 }
        return min(1.0, CGFloat(spent / cap))
    }
}

// ─── Main header ─────────────────────────────────────────────────
struct MainHeader: View {
    let nav: MainWindow.Nav

    private var title: String {
        switch nav {
        case .home:      return "Home"
        case .workflows: return "Workflows"
        case .author:    return "Author"
        case .runs:      return "Runs"
        case .settings:  return "Settings"
        }
    }

    private var subtitle: String? {
        switch nav {
        case .home:
            return Self.todayString()
        case .workflows:
            let total = MockData.workflows.count
            let scheduled = MockData.workflows.filter { $0.schedule != nil }.count
            return "\(total) saved · \(scheduled) scheduled"
        case .author:
            return "Describe a task → Claude drafts YAML"
        case .runs:
            let live = MockData.runs.filter { $0.status == .running }.count
            let failed = MockData.runs.filter { $0.status == .failed }.count
            return "\(live) live · \(failed) failed today"
        case .settings:
            return "System · budget · permissions"
        }
    }

    private static func todayString() -> String {
        let f = DateFormatter()
        f.dateFormat = "EEEE, MMMM d"
        return f.string(from: Date())
    }

    var body: some View {
        HStack(alignment: .center, spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(PFont.display(18, weight: .semibold))
                    .kerning(-0.4)
                    .foregroundStyle(PColor.fg0)
                if let subtitle {
                    Text(subtitle)
                        .font(PFont.ui(12))
                        .foregroundStyle(PColor.fg2)
                }
            }
            Spacer()
            if nav == .workflows || nav == .runs {
                SearchBox()
            }
            if nav == .home {
                Image(systemName: "arrow.clockwise")
                    .font(.system(size: 13))
                    .foregroundStyle(PColor.fg1)
                    .padding(8)
                    .overlay(RoundedRectangle(cornerRadius: PRadius.md)
                        .stroke(PColor.lineSoft, lineWidth: 0.5))
            }
        }
        .padding(.horizontal, PSpace.xl)
        .padding(.vertical, 14)
        .frame(minHeight: 56)
        .background(PColor.bg1)
    }
}

private struct SearchBox: View {
    @State private var query: String = ""
    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "magnifyingglass")
                .font(.system(size: 11))
                .foregroundStyle(PColor.fg3)
            TextField("Search workflows, runs…", text: $query)
                .textFieldStyle(.plain)
                .font(PFont.ui(12.5))
                .foregroundStyle(PColor.fg0)
            Text("⌘K")
                .font(PFont.mono(10))
                .foregroundStyle(PColor.fg3)
                .padding(.horizontal, 5)
                .padding(.vertical, 1)
                .overlay(RoundedRectangle(cornerRadius: 4)
                    .stroke(PColor.line, lineWidth: 0.5))
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .frame(width: 260)
        .background(PColor.bg3)
        .overlay(RoundedRectangle(cornerRadius: PRadius.md)
            .stroke(PColor.lineSoft, lineWidth: 0.5))
        .clipShape(RoundedRectangle(cornerRadius: PRadius.md))
    }
}

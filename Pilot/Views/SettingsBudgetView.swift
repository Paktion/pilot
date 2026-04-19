import SwiftUI

struct SettingsBudget: View {
    @EnvironmentObject var appState: AppState

    var body: some View {
        let usage = appState.data.usage
        VStack(alignment: .leading, spacing: PSpace.l) {
            HStack(spacing: 14) {
                bigCard(
                    label: "Today",
                    spent: usage.dailyCost,
                    cap: usage.dailyBudget,
                    sub: "Resets at midnight Pacific"
                )
                bigCard(
                    label: "This month",
                    spent: usage.monthlyCost,
                    cap: usage.monthlyBudget,
                    sub: monthlySub(usage: usage)
                )
            }

            kvCard

            costByWorkflowCard
        }
        .task { await appState.data.refreshUsage() }
    }

    private func monthlySub(usage: PilotData.UsageSummary) -> String {
        guard usage.monthlyBudget > 0 else { return "No monthly cap set" }
        let pct = Int((usage.monthlyCost / usage.monthlyBudget) * 100)
        return "\(pct)% of $\(String(format: "%.0f", usage.monthlyBudget)) cap used"
    }

    private var avgCostPerRun: Double {
        let runs = appState.data.runs
        guard !runs.isEmpty else { return 0 }
        return runs.map(\.cost).reduce(0, +) / Double(runs.count)
    }

    private func bigCard(label: String, spent: Double, cap: Double, sub: String) -> some View {
        let pct = cap > 0 ? min(1.0, spent / cap) : 0
        return VStack(alignment: .leading, spacing: 8) {
            Text(label).kicker()
            HStack(alignment: .firstTextBaseline, spacing: 0) {
                Text(String(format: "$%.3f", spent))
                    .font(PFont.display(32, weight: .semibold))
                    .foregroundStyle(PColor.fg0)
                Text(String(format: " / $%.2f", cap))
                    .font(PFont.display(16, weight: .regular))
                    .foregroundStyle(PColor.fg2)
            }
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 2.5)
                        .fill(PColor.bg4)
                    RoundedRectangle(cornerRadius: 2.5)
                        .fill(PColor.signal)
                        .frame(width: geo.size.width * pct)
                }
            }
            .frame(height: 5)
            Text(sub)
                .font(PFont.ui(11.5))
                .foregroundStyle(PColor.fg2)
                .padding(.top, 2)
        }
        .padding(PSpace.l)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(PColor.bg2)
        .overlay(
            RoundedRectangle(cornerRadius: PRadius.lg)
                .stroke(PColor.lineSoft, lineWidth: 0.5)
        )
        .clipShape(RoundedRectangle(cornerRadius: PRadius.lg))
    }

    private var kvCard: some View {
        let usage = appState.data.usage
        return SetKVCard {
            SetKVLine(key: "Per-task cap",
                      value: String(format: "$%.2f", usage.perTaskBudget))
            SetDivider()
            SetKVLine(key: "Total API calls", value: "\(usage.totalCalls)")
            SetDivider()
            SetKVLine(key: "Avg cost per run",
                      value: String(format: "$%.3f", avgCostPerRun))
        }
    }

    private var costByWorkflowCard: some View {
        // TODO(daemon): expose usage.byWorkflow(days=30)
        PCard {
            VStack(alignment: .leading, spacing: PSpace.m) {
                Text("Cost by workflow · last 30 days")
                    .font(PFont.ui(13, weight: .semibold))
                    .foregroundStyle(PColor.fg0)
                VStack(spacing: 10) {
                    ForEach(Array(MockData.costByWorkflow.enumerated()), id: \.offset) { _, entry in
                        let (name, cost, app) = entry
                        HStack(spacing: PSpace.m) {
                            AppMark(app: app, size: 20)
                            Text(name)
                                .font(PFont.ui(12.5))
                                .foregroundStyle(PColor.fg0)
                                .lineLimit(1)
                                .truncationMode(.tail)
                            Spacer(minLength: 0)
                            ZStack(alignment: .leading) {
                                RoundedRectangle(cornerRadius: 3)
                                    .fill(PColor.bg3)
                                RoundedRectangle(cornerRadius: 3)
                                    .fill(
                                        LinearGradient(
                                            colors: [PColor.signal, PColor.signal.opacity(0.6)],
                                            startPoint: .leading, endPoint: .trailing
                                        )
                                    )
                                    .frame(width: 180 * min(1.0, cost / 1.5))
                            }
                            .frame(width: 180, height: 6)
                            Text(String(format: "$%.2f", cost))
                                .font(PFont.mono(12))
                                .foregroundStyle(PColor.fg0)
                                .frame(width: 56, alignment: .trailing)
                        }
                    }
                }
            }
        }
    }
}

struct SetKVCard<Content: View>: View {
    @ViewBuilder var content: Content
    var body: some View {
        VStack(spacing: 0) { content }
            .background(PColor.bg2)
            .overlay(
                RoundedRectangle(cornerRadius: PRadius.lg)
                    .stroke(PColor.lineSoft, lineWidth: 0.5)
            )
            .clipShape(RoundedRectangle(cornerRadius: PRadius.lg))
    }
}

struct SetKVLine: View {
    let key: String
    let value: String
    var dim: Bool = false
    var mono: Bool = true
    var valueColor: Color? = nil
    var body: some View {
        HStack {
            Text(key).font(PFont.ui(12.5)).foregroundStyle(PColor.fg1)
            Spacer()
            Text(value)
                .font(mono ? PFont.mono(12.5) : PFont.ui(12.5))
                .foregroundStyle(valueColor ?? (dim ? PColor.fg2 : PColor.fg0))
                .lineLimit(1)
                .truncationMode(.middle)
        }
        .padding(.horizontal, PSpace.l)
        .padding(.vertical, PSpace.m)
    }
}

struct SetDivider: View {
    var body: some View { Rectangle().fill(PColor.lineSoft).frame(height: 0.5) }
}

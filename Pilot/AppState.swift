import Foundation
import Combine

@MainActor
final class AppState: ObservableObject {
    @Published var daemonConnected: Bool = false
    @Published var daemonVersion: String = ""
    @Published var activeRunID: String? = nil
    @Published var lastError: String? = nil
    @Published var dailyCost: Double = 0
    @Published var dailyBudget: Double = 5.0
    @Published var showOnboarding: Bool = false

    let client: DaemonClient
    private var costRefreshTask: Task<Void, Never>?

    init() {
        self.client = DaemonClient()
    }

    func startCostRefresh() {
        costRefreshTask?.cancel()
        costRefreshTask = Task { @MainActor [weak self] in
            guard let self else { return }
            while !Task.isCancelled {
                await self.refreshCost()
                try? await Task.sleep(nanoseconds: 10_000_000_000)  // 10s
            }
        }
    }

    private func refreshCost() async {
        if !client.isConnected { await client.connect() }
        if let usage = try? await client.callOnce(method: "usage.summary") {
            self.dailyCost = usage["daily_cost"] as? Double ?? 0
            self.dailyBudget = usage["daily_budget"] as? Double ?? 5.0
        }
    }
}

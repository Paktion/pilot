import Foundation
import Combine

@MainActor
final class AppState: ObservableObject {
    @Published var daemonConnected: Bool = false
    @Published var daemonVersion: String = ""
    @Published var activeRunID: String? = nil
    @Published var lastError: String? = nil

    let client: DaemonClient

    init() {
        self.client = DaemonClient()
    }
}

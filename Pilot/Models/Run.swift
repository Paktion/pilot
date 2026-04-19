import Foundation

struct Run: Identifiable, Codable, Hashable {
    enum Status: String, Codable { case success, failed, aborted, skipped, running }

    let id: String
    let workflowID: String
    let startedAt: Date
    var endedAt: Date?
    var status: Status
    var summary: String
    var costUSD: Double
    var sessionPath: String?
}

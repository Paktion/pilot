import Foundation

struct ScheduleEntry: Identifiable, Codable, Hashable {
    let id: String
    let workflowID: String
    var cronExpr: String
    var enabled: Bool
    var lastFiredAt: Date?
}

import Foundation

struct Workflow: Identifiable, Codable, Hashable {
    let id: String
    var name: String
    var app: String
    var tags: [String]
    var description: String
    var steps: [Step]
    var lastRunAt: Date?
    var runCount: Int
    var successCount: Int
    var compiledPath: String?
}

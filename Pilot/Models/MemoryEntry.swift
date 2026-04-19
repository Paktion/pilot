import Foundation

struct MemoryEntry: Identifiable, Codable, Hashable {
    enum Kind: String, Codable {
        case preference, extracted, observation, fact
    }

    let id: String
    let workflowID: String?
    let runID: String?
    var kind: Kind
    var key: String
    var valueJSON: String
    let createdAt: Date
}

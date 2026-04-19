import Foundation

struct Step: Identifiable, Codable, Hashable {
    enum Kind: String, Codable, CaseIterable {
        case launch, waitFor = "wait_for", tap, tapNear = "tap_near", tapXY = "tap_xy"
        case swipe, typeText = "type_text", pressKey = "press_key"
        case readAs = "read_as", remember, abortIf = "abort_if"
        case screenshot, done
    }

    let id: UUID
    var kind: Kind
    var label: String
    var raw: [String: String]
}

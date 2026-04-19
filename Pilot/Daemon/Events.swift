import Foundation

enum DaemonEvent: Decodable {
    case started(requestID: String, runID: String)
    case step(requestID: String, step: Int, thought: String, action: String, target: String?)
    case approvalNeeded(requestID: String, step: Int, action: String, x: Int, y: Int, label: String)
    case done(requestID: String, status: String, summary: String?, costUSD: Double?)
    case error(requestID: String?, message: String)
    case status(requestID: String, payload: [String: AnyCodable])

    private enum CodingKeys: String, CodingKey {
        case requestID = "request_id"
        case event, runID = "run_id", step, thought, action, target, x, y, label
        case status, summary, costUSD = "cost_usd", error
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        let requestID = try c.decodeIfPresent(String.self, forKey: .requestID) ?? ""
        let event = try c.decodeIfPresent(String.self, forKey: .event) ?? ""
        switch event {
        case "started":
            let runID = try c.decodeIfPresent(String.self, forKey: .runID) ?? ""
            self = .started(requestID: requestID, runID: runID)
        case "step":
            self = .step(
                requestID: requestID,
                step: try c.decodeIfPresent(Int.self, forKey: .step) ?? 0,
                thought: try c.decodeIfPresent(String.self, forKey: .thought) ?? "",
                action: try c.decodeIfPresent(String.self, forKey: .action) ?? "",
                target: try c.decodeIfPresent(String.self, forKey: .target)
            )
        case "approval_needed":
            self = .approvalNeeded(
                requestID: requestID,
                step: try c.decodeIfPresent(Int.self, forKey: .step) ?? 0,
                action: try c.decodeIfPresent(String.self, forKey: .action) ?? "",
                x: try c.decodeIfPresent(Int.self, forKey: .x) ?? 0,
                y: try c.decodeIfPresent(Int.self, forKey: .y) ?? 0,
                label: try c.decodeIfPresent(String.self, forKey: .label) ?? ""
            )
        case "done":
            self = .done(
                requestID: requestID,
                status: try c.decodeIfPresent(String.self, forKey: .status) ?? "",
                summary: try c.decodeIfPresent(String.self, forKey: .summary),
                costUSD: try c.decodeIfPresent(Double.self, forKey: .costUSD)
            )
        case "error":
            self = .error(
                requestID: requestID.isEmpty ? nil : requestID,
                message: try c.decodeIfPresent(String.self, forKey: .error) ?? "unknown error"
            )
        default:
            let payload = try decoder.singleValueContainer().decode([String: AnyCodable].self)
            self = .status(requestID: requestID, payload: payload)
        }
    }
}

struct AnyCodable: Codable {
    let value: Any

    init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if let v = try? c.decode(Bool.self) { self.value = v; return }
        if let v = try? c.decode(Int.self) { self.value = v; return }
        if let v = try? c.decode(Double.self) { self.value = v; return }
        if let v = try? c.decode(String.self) { self.value = v; return }
        if let v = try? c.decode([AnyCodable].self) { self.value = v.map(\.value); return }
        if let v = try? c.decode([String: AnyCodable].self) {
            self.value = v.mapValues(\.value); return
        }
        self.value = NSNull()
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch value {
        case let v as Bool: try c.encode(v)
        case let v as Int: try c.encode(v)
        case let v as Double: try c.encode(v)
        case let v as String: try c.encode(v)
        case let v as [Any]:
            try c.encode(v.map(AnyCodable.init(any:)))
        case let v as [String: Any]:
            try c.encode(v.mapValues(AnyCodable.init(any:)))
        default: try c.encodeNil()
        }
    }

    init(any: Any) { self.value = any }
}

import Foundation

struct RPCRequest: Encodable {
    let requestID: String
    let method: String
    let params: [String: String]?

    enum CodingKeys: String, CodingKey {
        case requestID = "request_id"
        case method, params
    }

    static func healthCheck() -> RPCRequest {
        RPCRequest(requestID: UUID().uuidString, method: "health.check", params: nil)
    }

    static func workflowList() -> RPCRequest {
        RPCRequest(requestID: UUID().uuidString, method: "workflow.list", params: nil)
    }

    static func workflowRun(name: String) -> RPCRequest {
        RPCRequest(requestID: UUID().uuidString, method: "workflow.run", params: ["name": name])
    }
}

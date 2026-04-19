import SwiftUI

struct SessionReplayView: View {
    let runID: String

    var body: some View {
        Text("Session replay for run \(runID) (M9)")
            .foregroundStyle(.secondary)
    }
}

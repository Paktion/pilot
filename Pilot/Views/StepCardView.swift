import SwiftUI

struct StepCardView: View {
    let step: Step

    var body: some View {
        VStack(alignment: .leading) {
            Text(step.kind.rawValue).font(.headline)
            Text(step.label).font(.caption).foregroundStyle(.secondary)
        }
        .padding(8)
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 8))
    }
}

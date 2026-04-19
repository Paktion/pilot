import SwiftUI

struct FlowChips: View {
    let prompts: [String]
    let onTap: (String) -> Void

    var body: some View {
        FlexibleHStack(spacing: 6, runSpacing: 6) {
            ForEach(prompts, id: \.self) { p in
                Button { onTap(p) } label: {
                    Text(p)
                        .font(PFont.ui(11.5))
                        .foregroundStyle(PColor.fg1)
                        .lineLimit(1)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 5)
                        .background(PColor.bg3)
                        .overlay(
                            Capsule().stroke(PColor.lineSoft, lineWidth: 0.5)
                        )
                        .clipShape(Capsule())
                }
                .buttonStyle(.plain)
            }
        }
    }
}

struct FlexibleHStack<Content: View>: View {
    let spacing: CGFloat
    let runSpacing: CGFloat
    @ViewBuilder let content: () -> Content

    var body: some View {
        _FlowLayout(spacing: spacing, runSpacing: runSpacing) {
            content()
        }
    }
}

private struct _FlowLayout: Layout {
    let spacing: CGFloat
    let runSpacing: CGFloat

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let maxW = proposal.width ?? .infinity
        var x: CGFloat = 0
        var y: CGFloat = 0
        var rowH: CGFloat = 0
        var totalW: CGFloat = 0
        for sv in subviews {
            let s = sv.sizeThatFits(.unspecified)
            if x + s.width > maxW, x > 0 {
                y += rowH + runSpacing
                x = 0
                rowH = 0
            }
            x += s.width + spacing
            rowH = max(rowH, s.height)
            totalW = max(totalW, x)
        }
        return CGSize(width: min(totalW, maxW), height: y + rowH)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let maxW = bounds.width
        var x: CGFloat = bounds.minX
        var y: CGFloat = bounds.minY
        var rowH: CGFloat = 0
        for sv in subviews {
            let s = sv.sizeThatFits(.unspecified)
            if x + s.width > bounds.minX + maxW, x > bounds.minX {
                y += rowH + runSpacing
                x = bounds.minX
                rowH = 0
            }
            sv.place(at: CGPoint(x: x, y: y), proposal: ProposedViewSize(s))
            x += s.width + spacing
            rowH = max(rowH, s.height)
        }
    }
}

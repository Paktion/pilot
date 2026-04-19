import SwiftUI

// Shared building blocks: app marks, sparklines, chips, buttons, sparkbar.
// Mirrors the JSX prototype's chrome.jsx + the chip / btn primitives in styles.css.

// ─── App brand mark ────────────────────────────────────────────────
// Per-app monogram tile used everywhere (sidebar nav, workflow cards,
// run rows, drawer header). Tints chosen to match prototype.
struct AppMark: View {
    let app: String
    var size: CGFloat = 28

    private var tint: Color {
        switch app {
        case "Ohio State": return Color(red: 0.45, green: 0.18, blue: 0.13) // brick
        case "Grubhub":    return Color(red: 0.52, green: 0.62, blue: 0.18)
        case "Weather":    return Color(red: 0.20, green: 0.36, blue: 0.55)
        case "Spotify":    return Color(red: 0.20, green: 0.55, blue: 0.30)
        case "Uber":       return Color(red: 0.18, green: 0.18, blue: 0.18)
        case "Notes":      return Color(red: 0.65, green: 0.55, blue: 0.20)
        default:           return Color(red: 0.32, green: 0.30, blue: 0.27)
        }
    }
    private var letter: String {
        switch app {
        case "Ohio State": return "O"
        case "Grubhub":    return "G"
        case "Weather":    return "W"
        case "Spotify":    return "S"
        case "Uber":       return "U"
        case "Notes":      return "N"
        default:           return String(app.prefix(1))
        }
    }

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: size * 0.28)
                .fill(tint)
            Text(letter)
                .font(PFont.display(size * 0.45, weight: .semibold))
                .foregroundStyle(PColor.fg0)
        }
        .frame(width: size, height: size)
        .overlay(
            RoundedRectangle(cornerRadius: size * 0.28)
                .stroke(Color.white.opacity(0.12), lineWidth: 0.5)
        )
    }
}

// ─── Sparkline ────────────────────────────────────────────────────
// Tiny per-run health bars: 1 = success (signal), -1 = failed (bad), 0 = no run (bg-4).
struct Sparkline: View {
    let data: [Int]
    var width: CGFloat = 72
    var height: CGFloat = 20

    var body: some View {
        GeometryReader { geo in
            let cellW = geo.size.width / CGFloat(max(data.count, 1))
            HStack(spacing: 1) {
                ForEach(Array(data.enumerated()), id: \.offset) { _, v in
                    let h: CGFloat = v == 0 ? 3 : max(4, geo.size.height - 2)
                    RoundedRectangle(cornerRadius: 1.2)
                        .fill(barColor(v))
                        .frame(width: max(2, cellW - 2), height: h)
                        .frame(maxHeight: .infinity, alignment: .bottom)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .frame(width: width, height: height)
    }

    private func barColor(_ v: Int) -> Color {
        switch v {
        case 1:  return PColor.signal
        case -1: return PColor.bad
        default: return PColor.bg4
        }
    }
}

// ─── Chip ─────────────────────────────────────────────────────────
struct Chip: View {
    enum Tone { case neutral, signal, ok, warn, bad }
    let text: String
    var tone: Tone = .neutral
    var dot: Bool = false

    var body: some View {
        HStack(spacing: 5) {
            if dot {
                Circle().fill(currentColor).frame(width: 6, height: 6)
            }
            Text(text)
                .font(PFont.ui(11, weight: .medium))
                .lineLimit(1)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 3)
        .foregroundStyle(currentColor)
        .background(currentBg)
        .clipShape(Capsule())
        .overlay(
            Capsule().stroke(borderColor, lineWidth: 0.5)
        )
    }

    private var currentColor: Color {
        switch tone {
        case .neutral: return PColor.fg1
        case .signal:  return PColor.signal
        case .ok:      return PColor.ok
        case .warn:    return PColor.warn
        case .bad:     return PColor.bad
        }
    }
    private var currentBg: Color {
        switch tone {
        case .neutral: return PColor.bg3
        case .signal:  return PColor.signalDim
        case .ok:      return PColor.ok.opacity(0.15)
        case .warn:    return PColor.warn.opacity(0.15)
        case .bad:     return PColor.bad.opacity(0.15)
        }
    }
    private var borderColor: Color {
        tone == .neutral ? PColor.lineSoft : .clear
    }
}

// ─── Buttons ──────────────────────────────────────────────────────
struct PButton: View {
    enum Variant { case primary, ghost, danger, secondary }
    enum Size { case regular, small, icon }

    let title: String
    var icon: String? = nil
    var variant: Variant = .secondary
    var size: Size = .regular
    var action: () -> Void

    init(_ title: String,
         icon: String? = nil,
         variant: Variant = .secondary,
         size: Size = .regular,
         action: @escaping () -> Void) {
        self.title = title
        self.icon = icon
        self.variant = variant
        self.size = size
        self.action = action
    }

    var body: some View {
        Button(action: action) {
            HStack(spacing: 6) {
                if let icon { Image(systemName: icon).font(iconFont) }
                if !title.isEmpty {
                    Text(title)
                        .font(PFont.ui(textSize, weight: .medium))
                        .lineLimit(1)
                }
            }
            .padding(.horizontal, hPad)
            .padding(.vertical, vPad)
            .frame(minWidth: minWidth, minHeight: minHeight)
            .foregroundStyle(fg)
            .background(bg)
            .overlay(
                RoundedRectangle(cornerRadius: radius)
                    .stroke(border, lineWidth: 0.5)
            )
            .clipShape(RoundedRectangle(cornerRadius: radius))
        }
        .buttonStyle(.plain)
    }

    private var fg: Color {
        switch variant {
        case .primary:   return PColor.signalInk
        case .ghost:     return PColor.fg1
        case .danger:    return PColor.bad
        case .secondary: return PColor.fg0
        }
    }
    private var bg: Color {
        switch variant {
        case .primary:   return PColor.signal
        case .ghost:     return .clear
        case .danger:    return .clear
        case .secondary: return PColor.bg3
        }
    }
    private var border: Color {
        switch variant {
        case .primary:   return .clear
        case .ghost:     return PColor.lineSoft
        case .danger:    return PColor.lineSoft
        case .secondary: return PColor.line
        }
    }
    private var radius: CGFloat { size == .small ? 7 : PRadius.md }
    private var hPad: CGFloat {
        switch size { case .small: return 9; case .icon: return 0; case .regular: return 12 }
    }
    private var vPad: CGFloat {
        switch size { case .small: return 4; case .icon: return 0; case .regular: return 6 }
    }
    private var textSize: CGFloat { size == .small ? 11.5 : 12.5 }
    private var iconFont: Font { .system(size: size == .small ? 10 : 12, weight: .medium) }
    private var minWidth: CGFloat? { size == .icon ? 30 : nil }
    private var minHeight: CGFloat? { size == .icon ? 30 : nil }
}

// ─── Status dot ──────────────────────────────────────────────────
// "dotlg" in the prototype: solid dot with a tinted halo ring.
struct StatusDot: View {
    enum Tone { case ok, warn, bad, signal }
    let tone: Tone
    var size: CGFloat = 8

    var body: some View {
        Circle()
            .fill(color)
            .frame(width: size, height: size)
            .overlay(
                Circle()
                    .stroke(color.opacity(0.18), lineWidth: 3)
            )
    }
    private var color: Color {
        switch tone {
        case .ok:     return PColor.ok
        case .warn:   return PColor.warn
        case .bad:    return PColor.bad
        case .signal: return PColor.signal
        }
    }
}

// ─── Group container card ───────────────────────────────────────
struct PCard<Content: View>: View {
    var elevated: Bool = false
    @ViewBuilder var content: Content

    var body: some View {
        content
            .padding(PSpace.l)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(elevated ? PColor.bg3 : PColor.bg2)
            .overlay(
                RoundedRectangle(cornerRadius: PRadius.lg)
                    .stroke(PColor.lineSoft, lineWidth: 0.5)
            )
            .clipShape(RoundedRectangle(cornerRadius: PRadius.lg))
    }
}

// ─── Key/value row used in Settings, Drawer ─────────────────────
struct KVRow: View {
    let key: String
    let value: String
    var valueMono: Bool = true
    var valueColor: Color = PColor.fg0

    var body: some View {
        HStack {
            Text(key).foregroundStyle(PColor.fg2)
            Spacer()
            Text(value)
                .font(valueMono ? PFont.mono(12.5) : PFont.ui(12.5))
                .foregroundStyle(valueColor)
        }
        .font(PFont.ui(12.5))
        .padding(.horizontal, PSpace.l)
        .padding(.vertical, PSpace.m)
        .overlay(alignment: .top) {
            Rectangle()
                .fill(PColor.lineSoft)
                .frame(height: 0.5)
        }
    }
}

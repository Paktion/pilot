import SwiftUI

// Design tokens for the Pilot revamp.
// Palette is "warm-neutral dark" — slight brown undertone rather than pure gray —
// with a single signal color (warm lime-green) used for status / accent.
// Original OKLCH values from styles.css are noted in comments; sRGB approximations
// here are eyeballed to match the prototype's visual weight.

enum PColor {
    // Background scale (deepest → highest elevation)
    static let bg0 = Color(red: 0.105, green: 0.099, blue: 0.090)   // oklch(0.18 0.005 60) — outside / canvas
    static let bg1 = Color(red: 0.130, green: 0.123, blue: 0.112)   // oklch(0.21 0.006 60) — window
    static let bg2 = Color(red: 0.155, green: 0.146, blue: 0.133)   // oklch(0.24 0.006 60) — sidebar / cards
    static let bg3 = Color(red: 0.190, green: 0.180, blue: 0.163)   // oklch(0.28 0.007 60) — elevated cards / buttons
    static let bg4 = Color(red: 0.235, green: 0.222, blue: 0.200)   // oklch(0.33 0.008 60) — hover / borders

    // Foreground scale (primary → quaternary)
    static let fg0 = Color(red: 0.960, green: 0.950, blue: 0.930)   // oklch(0.96 0.004 90)
    static let fg1 = Color(red: 0.745, green: 0.725, blue: 0.690)   // oklch(0.78 0.006 80)
    static let fg2 = Color(red: 0.510, green: 0.495, blue: 0.470)   // oklch(0.58 0.006 80)
    static let fg3 = Color(red: 0.355, green: 0.345, blue: 0.325)   // oklch(0.42 0.006 80)

    // Lines / dividers
    static let line     = Color(red: 0.225, green: 0.215, blue: 0.195).opacity(0.7)
    static let lineSoft = Color(red: 0.190, green: 0.182, blue: 0.165).opacity(0.55)

    // Signal (warm lime-green) and tinted variants
    static let signal     = Color(red: 0.745, green: 0.860, blue: 0.420)  // oklch(0.82 0.18 130)
    static let signalDim  = Color(red: 0.745, green: 0.860, blue: 0.420).opacity(0.18)
    static let signalInk  = Color(red: 0.130, green: 0.220, blue: 0.060)  // dark text on signal-bg

    // Status colors
    static let ok   = Color(red: 0.510, green: 0.820, blue: 0.560)   // oklch(0.76 0.15 145)
    static let warn = Color(red: 0.850, green: 0.720, blue: 0.300)   // oklch(0.80 0.16 85)
    static let bad  = Color(red: 0.860, green: 0.500, blue: 0.380)   // oklch(0.70 0.18 25)
    static let info = Color(red: 0.460, green: 0.715, blue: 0.860)   // oklch(0.75 0.12 235)
}

enum PRadius {
    static let sm: CGFloat = 6
    static let md: CGFloat = 10
    static let lg: CGFloat = 14
    static let xl: CGFloat = 20
}

enum PSpace {
    static let xs: CGFloat = 4
    static let s:  CGFloat = 8
    static let m:  CGFloat = 12
    static let l:  CGFloat = 16
    static let xl: CGFloat = 24
}

// Typography. Inter / Inter Tight / Geist Mono are not bundled — we fall back to
// SF Pro variants. Keep usage centralized here so a future font-bundling pass
// only needs to swap these returns.
enum PFont {
    static func ui(_ size: CGFloat, weight: Font.Weight = .regular) -> Font {
        .system(size: size, weight: weight, design: .default)
    }
    static func display(_ size: CGFloat, weight: Font.Weight = .semibold) -> Font {
        // Inter Tight is a tighter display sibling; SF Pro Display is the closest
        // shipped variant on macOS. Use slightly tighter tracking via .kerning at sites.
        .system(size: size, weight: weight, design: .default)
    }
    static func mono(_ size: CGFloat, weight: Font.Weight = .regular) -> Font {
        .system(size: size, weight: weight, design: .monospaced)
    }
}

// Common modifiers
extension View {
    func cardBackground(elevated: Bool = false) -> some View {
        self
            .background(elevated ? PColor.bg3 : PColor.bg2)
            .overlay(
                RoundedRectangle(cornerRadius: PRadius.lg)
                    .stroke(PColor.lineSoft, lineWidth: 0.5)
            )
            .clipShape(RoundedRectangle(cornerRadius: PRadius.lg))
    }

    /// Mono uppercase eyebrow label used throughout the design (".kicker" in CSS).
    func kicker() -> some View {
        self
            .font(PFont.mono(10.5, weight: .medium))
            .tracking(1.2)
            .textCase(.uppercase)
            .foregroundStyle(PColor.fg3)
    }
}

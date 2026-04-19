# Pilot — app icon handoff

White paper airplane on black. Side-profile silhouette.

## Files

| File | Use |
|---|---|
| `pilot-icon.svg` | Master — 1024×1024 with rounded iOS squircle mask |
| `pilot-mark.svg` | Bare mark, transparent background (white plane) |
| `pilot-mark-inverse.svg` | Bare mark for light surfaces (black plane) |
| `favicon.svg` | Simplified favicon, tuned stroke weights |
| `pilot-icon-{size}.png` | Raster exports: 1024, 512, 256, 180, 128, 64, 32 |

## Colors

| Token | Hex | Notes |
|---|---|---|
| Background | `#000000` | Pure black |
| Plane (primary) | `#ffffff` | Pure white |
| Plane (wing, folded) | `#ffffff` @ 50% opacity | Renders as mid-gray on black |
| Fold lines | `#000000` | Cut into the white shape to show creases |

## Geometry

All coordinates in a `1024 × 1024` viewBox. The plane sits on the lower-middle band, nose pointing **left**.

```
hull (underside):   M 120 590 → L 880 500 → L 640 620 → Z       (fill white)
top wing:           M 120 590 → L 880 500 → L 560 380 → Z       (fill white, 50% opacity)
body fold:          M 120 590 → L 640 620                       (stroke black, 6px)
wing leading fold:  M 880 500 → L 560 380                       (stroke black, 4px, 35% opacity)
```

iOS-style squircle corner radius on the 1024 frame: **230px** (≈ 22.5%).

## Safe area

The plane is inset roughly 12% from the nearest edge (left and top), 14% from the right, and 39% from the top. Keep a **96px clear zone** on all four sides when placing the mark on other backgrounds.

## Usage notes

- At sizes below 48px, use `favicon.svg` — stroke widths are beefed up so the fold lines don't disappear.
- The wing is intentionally translucent, not a flat tone. If you flatten it for a production pipeline, resolve to `#808080` (50% white on black).
- For monochrome contexts (e.g. Slack emoji, watchOS), drop the 35%-opacity wing fold; keep the solid hull and body fold.
- Do not rotate or skew the mark — the horizontal silhouette is the identity.

## Typography pairing (reference)

Marketing/display: **Instrument Serif** (italic for the product wordmark).
UI/text: **Geist** 400/500/600.
Mono/labels: **Geist Mono**.

All three are available on Google Fonts.

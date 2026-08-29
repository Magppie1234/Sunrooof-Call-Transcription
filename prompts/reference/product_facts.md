# SUNROOOF — approved product facts (authoritative)

**Precedence rule set by the user (2026-08-17):** when a technical detail or price
differs between sources, **the catalogue wins**. Sameer's training voice notes are
authoritative for *how to run a call*, but technical numbers spoken in them may
occasionally be wrong; the catalogue is the check.

Order of authority:
1. `SUNROOOF_Brand_catalogue A4.pdf` → extracted to `brand_catalogue.txt`
2. `Minimum console qty.pdf` (console quantity chart, below)
3. Technical specification sheet supplied by the user (below)
4. Sameer's training voice notes → `out/voice_notes/ALL_VOICE_NOTES.md`

Anything not covered by these is **unverifiable** — mark it `unknown`, never guess.

---

## Console specification

| Attribute | Approved value |
|---|---|
| Console size | **1200 mm × 400 mm** (4 ft × 1.4 ft) — consistent across catalogue and spec sheet |
| Console footprint | 5.6 sq ft |
| Drop-down depth | **13 inches / ~330 mm** from the RCC slab (catalogue: min 315–330 mm from ceiling, varies by model) |
| Wall-mounted depth | 150 mm from wall (French/Louvered), 315 mm (Arch) |
| Illumination coverage | **one console lights 5 ft × 5 ft** |
| Ideal ceiling height | **9 ft** (spec sheet also states 9–9.5 ft) |
| Lumen output | 4500–5300 lumens per console |
| Colour temperature | 2700 K – 6500 K |
| CRI | 98 |
| Dimming | 0–100% smooth |
| Drivers | DALI DT-8 (EU chips) |
| Controller | Casambi |
| Sensor | **Geolocation** |
| Power consumption | **20–40 W per console, maximum 50 W** |
| Frame materials | Pine, Teak, Raw wood, HDHMR |
| Console material | Tempered glass |
| Life span | **12–14 years** at 9–12 hours/day |
| Guarantee | **2 years** on all electronic components and rafters |
| Mobile support | iOS & Android |
| Application | Commercial and premium residential |
| Track record | **1000+ homes, offices, retail and other spaces transformed** |

## Product variants (catalogue)

Ceiling-mounted: **The Classical** (min 330 mm), **The Greens** (315 mm),
**The Minimalist** (315 mm), **Atrium** (mounted diagonally).
Wall-mounted: **French Window**, **Louvered Window** (fixed 1265 × 465 mm),
**Arch Window** (single = 4 consoles, double = 8 consoles; custom 12 ft / 3660 mm
available on request).

## Minimum suggested console quantity

| Room area | Minimum consoles |
|---|---|
| 100 – 120 sq ft | 4 |
| 121 – 150 sq ft | 6 |
| 151 – 450 sq ft | 8 |
| 451 – 550 sq ft | 10 |
| 551 – 774 sq ft | 12 |
| **775 sq ft and above** | **10% minimum coverage of room area** |

10% coverage formula: `(area × 0.10) ÷ 5.6 sq ft per console`.
Worked example from the chart: 775 sq ft → 77.5 ÷ 5.6 = **14 consoles**.

- **Absolute minimum is 4 consoles.** Above that, a customer may choose any higher
  quantity and that is acceptable.
- **Maximum coverage is 60–80% of the area** — quantity must never exceed that.

---

## Conflicts with the existing scorecard (catalogue wins)

The scorecard in `prompts/call_quality_audit.md` credits or requires several
figures that the approved sources contradict. Scoring must follow the right-hand
column.

| Scorecard says | Approved value | Effect |
|---|---|---|
| "900+ projects completed" (C3.4) | **1000+ spaces** | agent saying 1000+ is correct, not an error |
| "product life of 12-15 years" (C5.6) | **12–14 years** | 15 years is an overclaim |
| "power consumption 0.03 kW/hr" (C5.7) | **20–40 W, max 50 W** | 30 W sits inside the range; "0.03 kW/hr" is a unit error — kW is already a rate |
| "lower consumption than a 15W LED" (C5.7) | not supported anywhere | a 20–40 W console cannot draw less than a 15 W LED. **Do not score this as required, and treat an agent asserting it as a potential miss-sell** |
| "not sensor-based, works on GPS" (C5.10) | Sensor: **Geolocation** | both describe geolocation rather than occupancy sensing; an agent saying "geolocation" is correct |
| "four-console minimum" (C5.3, C6.5) | **confirmed — 4 minimum**, with the area chart above | consistent |

**Unresolved and still needed:** approved **price ranges** for ceiling and window
consoles, with effective dates. Nothing in the catalogue or spec sheet states
price, so Criterion 6's price sub-points remain unverifiable and must be scored
`unknown` rather than guessed.

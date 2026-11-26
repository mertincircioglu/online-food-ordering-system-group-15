# BiteFlow Design System (Generated with UI/UX Pro Max)

## 1. Visual Direction
- **Product Type:** Food Delivery / On-Demand Ordering Platform + Multi-Role SaaS Management Console
- **Style:** Vibrant & Warm Editorial Food-Tech (Light & Dark parity, crisp hierarchy, zero emoji UI icons)
- **Typography Pairing:**
  - **Headings:** `Outfit` (600, 700, 800) — geometric, bold, distinct display hierarchy
  - **Body & UI:** `Work Sans` (400, 500, 600, 700) — crisp readability across menus, forms, and SQL analytics tables with `tabular-nums`

## 2. Color Tokens (WCAG AA >= 4.5:1 Verified)
| Semantic Role | Light Mode | Dark Mode |
| :--- | :--- | :--- |
| Primary Brand | `#D9480F` (hover `#B83A0B`) | `#FB923C` (hover `#F97316`) |
| Trust Accent | `#2563EB` | `#60A5FA` |
| Page Canvas (`--bg`) | `#FFFBF7` | `#0B0F19` |
| Card Surface (`--surface`) | `#FFFFFF` | `#121826` |
| Elevated Surface (`--surface-alt`) | `#FDF6EF` | `#1A2234` |
| Primary Text (`--ink`) | `#111827` | `#F8FAFC` |
| Secondary Text (`--ink-soft`) | `#374151` | `#CBD5E1` |
| Muted Text (`--muted`) | `#525E70` | `#94A3B8` |
| Border (`--border`) | `#EEDFD2` | `#243045` |

## 3. Interaction & Accessibility Standards
- **Iconography:** 100% uniform 2px-stroke Lucide-style SVG icons (`_icons.html`), decorative icons marked `aria-hidden="true"`, icon-only controls labeled with `aria-label`.
- **Keyboard & Focus:** Visible 2px `:focus-visible` focus rings + Skip-to-Content link + `prefers-reduced-motion` support.
- **Touch Targets & Motion:** Minimum 40–44px interactive controls, 180–240ms smooth cubic-bezier transitions without layout shift.

# VaultWares Styles, Themes, Design Principles, and UI Guidelines

VaultWares applications must feel **modern, minimal, and polished** — not like a 1999 hacker movie. Every app ships with both a light and dark theme. Colorful, confident palettes are preferred over drab neutrals. Subtle motion and glassmorphism details are encouraged, but never at the expense of performance.

---

## 🔤 Typography

- **Default font:** `Segoe UI Semilight` for all body and UI text.
  - Fall back to: `system-ui`, then `sans-serif`.
  - Override this only when a feature or brand context explicitly calls for a different typeface.
- **Font weight:** Varies by context, but keep text light and airy as the baseline. Use heavier weights only for headings or emphasis.
- **Line height:** Use generous line-height (1.5–1.6 for body copy) to complement the semilight weight.
- **Letter spacing:** Slightly looser (`tracking-wide`) on headings; default on body.

---

## 🎨 Color Palettes

### Dark Themes

- **Base background:** Dark blue-gray — approximately `#4A5459`. Not pure black.
- **Surfaces / cards:** Slightly lighter than base, e.g., `#52606B`.
- **Accent options (pick one per theme):**
  - Gold amber: `#cc9b21`
  - Lime green: `#4ecc21`
  - Cyan teal: `#21b8cc`
  - Other vivid contrasting color
- **Reference:** [Solarized Dark](https://github.com/altercation/solarized) for tone and saturation guidance.

### Light Themes

- **Base background:** White or near-white — lighter than Solarized Light's `#fdf6e3`.
- **Surfaces / cards:** Subtle off-white or light gray (`#f8f8f8` to `#eeeeee` range).
- **Text:** Dark charcoal, not pure black — approximately `#333333` to `#4A4A4A`.
- **Reference:** [Solarized Light](https://github.com/altercation/solarized) for hue relationships, but with a whiter, brighter base.

### Gradients

- Gradients are encouraged when **discreet** — soft, low-contrast directional blends between two related hues.
- Avoid loud rainbow gradients. Use gradients as depth cues, not decoration.
- Good uses: card backgrounds, hero sections, sidebar accents, button hover states.

---

## 🖌️ Premade Skins

Use these skins when an app supports multiple themes. Format: `[mode] | [primary] | [accent]`.

| # | Mode | Primary Color | Accent Color |
| --- | ------ | -------------- | -------------- |
| 1 | Light | Light beige | Burgundy |
| 2 | Dark | Solarized `base02` (`#073642`) | Solarized orange (`#cb4b16`) |
| 3 | Dark | Dark gray (`#2d2d2d`) | Gold yellow (`#f0c040`) |
| 4 | Light | Off-white (`#f5f5f5`) | Darker gray (`#555555`) |
| 5 | Dark | Deep red (`#8b0000`) | Light pink (`#ffb6c1`) |
| 6 | Light | Light gray (`#e8e8e8`) | Deep sea blue (`#1a5276`) |
| 7 | Dark | Near-black (`#121212`) | VaultWares logo cyan (`#00bcd4`) or bright green (`#39ff14`) |
| 8 | Dark | Eggplant / violet (`#4b0082`) | Tangerine orange (`#ff6f00`) |
| 9 | Light | Pale white (`#fafafa`) | Bright purple (`#7c3aed`) |

**Implementation:** Accept a `themeIndex` (1–9) parameter at app initialization and apply the corresponding CSS custom properties or Tailwind theme extension.

---

## 💎 Glassmorphism (glass-ui)

Use the [glass-ui library](https://github.com/p-potvin/glass-ui) for glassmorphism effects. Apply in small doses:

- **Good uses:** Floating modals, nav bars over hero images, info cards on rich backgrounds, tooltips.
- **Avoid:** Using glass on every surface — it loses impact and hurts readability.
- **Backdrop blur:** Keep below `blur(12px)` on non-hero elements. Higher values are expensive on older GPUs.
- **Border:** A 1px semi-transparent white or light border (`rgba(255,255,255,0.18)`) adds depth without noise.
- **Background opacity:** `rgba(255,255,255,0.08)` to `rgba(255,255,255,0.15)` for dark themes; adjust for light themes.

---

## ✨ Motion & Animations

- **Philosophy:** Subtle and purposeful. Every animation should guide the user's attention or communicate state — not just decorate.
- **Hardware budget:** Assume a maximum 8-year-old GPU. Stick to `transform` and `opacity` animations (GPU-composited). Avoid animating `width`, `height`, `top`, `left`, or `box-shadow` unless unavoidable.
- **Duration guidelines:**
  - Micro-interactions (hover, focus): `100–150ms`
  - Component enter/exit (modal, drawer, tooltip): `150–250ms`
  - Page transitions: `200–300ms`
  - Never exceed `400ms` for functional UI feedback.
- **Easing:** Prefer `ease-out` for entrances, `ease-in` for exits, `ease-in-out` for loops.
- **Respect `prefers-reduced-motion`:** Wrap all non-essential animations in a media query check:

  ```css
  @media (prefers-reduced-motion: reduce) {
      * { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }
  }
  ```

- **Tailwind animations:** Use `transition`, `duration-*`, `ease-*`, and `animate-*` utilities. Add custom keyframes in `tailwind.config` only when needed.

---

## 🌗 Light / Dark Mode Implementation

- **Always support both modes.** No app ships with only one.
- **Implementation:** Use Tailwind's `dark:` variant with the `class` strategy (`darkMode: "class"` in `tailwind.config`).
- **Persistence:** Save the user's preference in `localStorage`. Respect `prefers-color-scheme` as the default.
- **Toggle:** Provide a visible, accessible theme toggle in the app header or settings panel.
- **Test both modes** before submitting a PR — check for contrast issues, invisible text, and broken glassmorphism effects.

---

## 🧩 Component Design Principles

- **React / Next.js:** Follow [Radix UI](https://www.radix-ui.com/) and Shadcn UI design patterns for interactive primitives (dialogs, dropdowns, tooltips). Extend them with Tailwind — do not replace them.
- **Spacing system:** Use Tailwind's spacing scale exclusively. No magic pixel values in inline styles.
- **Border radius:** Prefer `rounded-lg` (8px) to `rounded-xl` (12px) as the default card radius. Tighter for small inputs; looser only for full-bleed hero cards.
- **Shadows:** Prefer soft, layered shadows (`shadow-md`, `shadow-lg`) over harsh drop shadows. Use `shadow-inner` for pressed/inset states.
- **Responsiveness:** Design mobile-first. Every layout must be tested at 375px, 768px, 1280px, and 1920px breakpoints.
- **Accessibility:** All interactive elements must have visible focus rings (`focus-visible:ring-*`). Color alone must not convey meaning. Icon-only buttons require `aria-label`.

---

## 📐 Tailwind Configuration Conventions

- Define all brand colors as custom properties in `tailwind.config.ts` under `theme.extend.colors`.
- Prefix custom tokens with the project or brand name to avoid collisions (e.g., `vault-primary`, `vault-accent`).
- Do not use arbitrary value syntax (`text-[#cc9b21]`) for repeated design tokens — extract them into the config.
- Use `clsx` + `tailwind-merge` (`cn()` helper) to compose conditional class strings:

  ```typescript
  import { clsx } from "clsx";
  import { twMerge } from "tailwind-merge";
  export const cn = (...inputs: ClassValue[]) => twMerge(clsx(inputs));
  ```

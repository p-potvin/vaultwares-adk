# VaultWares — GitHub Copilot Theming Instructions

You are working in a VaultWares project. All code and UI must:
- Use only named design tokens for color, font, and spacing (see `Brand/tokens.ts`, `VaultThemeManager`, `VaultWares.Brand.xaml`)
- Never hardcode hex, px, or font values
- For React: use Tailwind classes and tokens
- For Python/Qt: use theme helpers
- For WinUI3/XAML: use resource dictionary keys
- All UI must meet accessibility (WCAG AA) and i18n requirements

Token Table:
| Token | Use |
|---|---|
| `vault-base` | Dark background |
| `vault-paper` / `vault-light` | Light background |
| `vault-gold` | Primary accent |
| `vault-cyan` | Interactive/links |
| `vault-green` | Success |
| `vault-burgundy` | Error |
| `vault-slate` | Secondary text |
| `vault-muted` | Captions |

See `skills/vault-designer/SKILL.md` for full usage patterns and rules.

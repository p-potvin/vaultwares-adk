# 🛡️ VaultWares Enterprise-wide Guidelines for Programming Projects

## What is VaultWares?

VaultWares is a privacy-first technology company that builds premium SaaS products, desktop applications, browser extensions, and open-source libraries. Every project shares a single north star: protecting users from data tracking, fingerprinting, and surveillance. Projects span web apps, real-time audio tools, Windows desktop utilities, Chrome extensions, and shared UI libraries — all united by a consistent tech stack and development philosophy.

Our first and most important mission is **individuals' privacy**. **Security is a close second** and exists to protect privacy. **Functionality is the third pillar**: the product must stay usable for regular people. Privacy and security are related but different: privacy limits and controls data; security protects what exists. Bad actors can weaponize “security” talk to push fear-driven surveillance. We aim to **strike the balance**: strong security in service of privacy, without privacy-eroding shortcuts.

These guidelines apply across the entire VaultWares umbrella. Use common sense to determine what is relevant to a given project. When in doubt, **prioritize in this order: privacy (individuals) → security → functionality/correctness → performance → scalability → developer experience.**

Always follow best practices for the specific language and framework in use, but treat the rules below as the baseline.

---

## 🚀 Core Tech Stack

The stack varies by project type. Choose the appropriate tier below.

### Web & Full-Stack Applications
| Concern | Preferred Choice |
|---|---|
| Framework | Next.js 15+ (App Router) or React 19 + Vite |
| Language | TypeScript (strict mode — no exceptions) |
| Styling | Tailwind CSS 4.x with light/dark mode support |
| State — server | TanStack Query (React Query) |
| State — client | Zustand (for non-trivial local state), React Context for simple cases |
| UI Primitives | Radix UI + Shadcn UI patterns |
| Glass effects | VaultWares `glass-ui` library (use in small doses) |
| Validation | Zod — for all API inputs, form data, and external responses |
| Icons | Lucide React |
| i18n | react-i18next (English + French at minimum) |
| HTTP | Native `fetch` with async/await; TanStack Query for caching |
| Testing | Vitest + Playwright for E2E; `@testing-library/react` for components |
| Build | Vite (frontend); tsx for running TypeScript server-side |

### Backend / API (Node.js)
| Concern | Preferred Choice |
|---|---|
| Runtime | Node.js with TypeScript (tsx) |
| Server | Express.js |
| Database | PostgreSQL via Google Cloud SQL (`pg` / node-postgres) |
| Auth | JWT (`jsonwebtoken`) + `bcryptjs` for password hashing |
| Secrets | GCP Secret Manager (never hardcode credentials) |
| Deployment | Google Cloud Run (containerized) |

### Python Applications (Desktop / ML / CLI)
| Concern | Preferred Choice |
|---|---|
| GUI | PySide6 (preferred over PyQt) |
| Audio | `sounddevice`, `pydub`, `soundfile` |
| ML / AI | `faster-whisper`, HuggingFace integration |
| Config | Environment variables + JSON config files |
| Packaging | pip + `requirements.txt`; virtual environment (`.venv`) always |
| Distribution | Windows `.cmd` wrapper script for CLI tools |

### Native Windows Applications (C#)
| Concern | Preferred Choice |
|---|---|
| Framework | .NET 8 + WinUI 3 (not WPF or UWP) |
| Architecture | MVVM with `CommunityToolkit.Mvvm` |
| UI Extension | WinUIEx |
| State | `ObservableCollection<T>` + `INotifyPropertyChanged` |
| Packaging | MSIX (x64, x86, arm64 builds) |

### Cloud Infrastructure
- **Primary platform:** Google Cloud Platform (Cloud Run, Cloud SQL, Cloud Build)
- **Database:** Cloud SQL — PostgreSQL. Connect via Unix socket on Cloud Run, TCP locally.
- **Secrets:** GCP Secret Manager. Access at runtime; never at build time.
- **CI/CD:** GitHub Actions pipelines + Google Cloud Build for deployments.

---

## 🏗️ Folder Structure

### TypeScript / React / Next.js Projects
```
src/
├── app/                  # Next.js App Router (pages, layouts, API routes)
├── components/
│   ├── ui/               # Atomic Shadcn/Radix primitives — do NOT modify directly
│   └── features/         # Feature-specific components (e.g., /cart, /checkout)
├── hooks/                # Custom React hooks (camelCase, use* prefix)
├── lib/                  # Utility functions, Zod schemas, shared helpers
├── types/                # Global TypeScript interfaces and type aliases
├── store/                # Zustand stores or React Context providers
├── styles/               # Global CSS, Tailwind configuration overrides
└── scripts/              # Extension scripts or build utilities
```

### Python Desktop / CLI Projects
```
project-root/
├── main_app.py           # Application entry point
├── module_name/          # Feature-scoped modules (snake_case)
│   ├── core_logic.py
│   ├── gui_overlay.py
│   └── ...
├── vault_sync.py         # Shared vault synchronization utility
├── requirements.txt
└── .venv/                # Local virtual environment (never committed)
```

### C# WinUI 3 Projects
```
ProjectName/
├── Models/               # Data models (AppSettings, BackupJob, etc.)
├── Services/             # Business logic (IService + concrete implementation)
├── ViewModels/           # MVVM ViewModels (INotifyPropertyChanged via CommunityToolkit)
├── Views/                # XAML UI files
├── Converters/           # Value converters for XAML binding
├── Themes/               # XAML ResourceDictionaries for light/dark themes
└── Assets/               # Images, icons, font files
```

---

## 🛠️ Coding Standards & Patterns

These rules apply regardless of language or project type.

### Universal Rules
- **Spaces around operators:** Write `x = 5`, never `x=5`.
- **Indentation:** 4 spaces. Never mix tabs and spaces.
- **Empty lines between logical blocks:** Separate imports, declarations, hooks, and return statements with a blank line for readability.
- **Comments inside functions:** Keep to a minimum. Define behavior at the function declaration (docstring or JSDoc), not inline. Exception: when calling a third-party library method with non-obvious defaults, leave a single-line comment explaining the key parameters and their implications.
- **No dead code:** Remove all debug statements, `console.log`, `print()`, unused imports, and commented-out code before committing.
- **DRY (Don't Repeat Yourself):** Before writing something new, search for an existing implementation. Check `@/components/ui` before adding UI elements; check `@/lib` before writing utility functions.

### TypeScript / JavaScript
- **Strict mode always:** `"strict": true` in `tsconfig.json`. No exceptions.
- **No `any`:** Use specific types. For truly dynamic data, use `unknown` and narrow with a type guard or Zod schema.
- **Use `interface` for objects, `type` for unions and primitives.**
- **Named exports only** for components and hooks (no default exports on components).
- **Functional components with arrow syntax:**
  ```tsx
  export const ProductCard = ({ name, price }: ProductCardProps) => {
      // ...
  };
  ```
- **Prefer Server Components** for data fetching. Use `"use client"` only when interactivity (events, hooks) is required.
- **Validate all inputs with Zod** before processing. Use `safeParse` and return a typed error on failure:
  ```typescript
  const result = createOrderSchema.safeParse(req.body);
  if (!result.success) {
      return res.status(400).json({ error: "Invalid payload", details: result.error.errors });
  }
  ```
- **Database queries must use parameterized queries** (`$1`, `$2`, …) — never string interpolation in SQL.
- **Transactions:** Wrap multi-step writes in explicit `BEGIN` / `COMMIT` / `ROLLBACK` blocks.
- **Mock fallback for development:** If the database is unavailable, fall back to mock data rather than crashing. Gate the fallback on an `isDbConnected()` check.

### Python
- **Virtual environment:** Always activate `.venv` before running `pip` or `python`. Never install to the global environment.
- **Class-based architecture** for stateful components (audio engines, GUI windows, background workers).
- **Thread safety:** Use `threading.Lock()` for shared mutable state accessed from multiple threads. Prefer daemon threads for background workers:
  ```python
  self.worker = threading.Thread(target=self._processing_loop, daemon=True)
  ```
- **Lazy initialization:** Load heavy models (ML models, audio backends) on first use, not at startup, to reduce launch time:
  ```python
  if self._model is None:
      self._model = load_model(...)
  ```
- **Logging:** Use `logging` module with rotating file handlers and a console handler. Toggle `DEBUG` level via an environment variable or config flag. Never use bare `print()` for application logging.
- **Type hints on all public methods and class attributes.** Use `Optional[T]` and `Union[A, B]` explicitly.

### C# / WinUI 3
- **MVVM strictly enforced:** No business logic in code-behind (`.xaml.cs`). All logic lives in ViewModels.
- **Null safety:** Enable `#nullable enable` in every file.
- **Private fields:** Use `_camelCase` prefix (e.g., `_backupJobs`, `_logger`).
- **Interfaces for services:** Define an `IMyService` interface and inject the concrete implementation. This enables testability and loose coupling.
- **Async/await throughout:** Use `Task`-returning methods and `await` them. Never block the UI thread with `.Result` or `.Wait()`.
- **Value converters for UI logic:** Do not place display-formatting logic in ViewModels; use XAML `IValueConverter` classes.

---

## 📛 Naming Conventions

### TypeScript / JavaScript
| Element | Convention | Example |
|---|---|---|
| React components | PascalCase | `ProductVault.tsx` |
| Custom hooks | camelCase, `use` prefix | `useVaultAuth.ts` |
| Utility / helper files | kebab-case | `format-currency.ts` |
| TypeScript interfaces | PascalCase | `CartContextType` |
| TypeScript type aliases | PascalCase | `PaymentStatus` |
| Constants | UPPER_SNAKE_CASE | `MAX_RETRY_COUNT` |
| Zod schemas | camelCase, `Schema` suffix | `createOrderSchema` |
| API route handlers | camelCase verbs | `getProducts`, `createOrder` |

### Python
| Element | Convention | Example |
|---|---|---|
| Classes | PascalCase | `RealTimeSTTApp` |
| Functions / methods | snake_case | `get_speech_prob()` |
| Module files | snake_case | `audio_capture.py` |
| Constants | UPPER_SNAKE_CASE | `MAX_SILENCE_CHUNKS` |
| Private methods | `_snake_case` | `_processing_loop()` |

### C#
| Element | Convention | Example |
|---|---|---|
| Classes / interfaces | PascalCase | `BackupService`, `IBackupService` |
| Properties | PascalCase | `BackupJobs`, `IsRunning` |
| Public methods | PascalCase | `ExecuteBackupAsync()` |
| Private fields | `_camelCase` | `_backupJobs` |
| Local variables | camelCase | `backupResult` |

---

## 🏆 Coding Best Practices

### Performance
- **React Suspense** for lazy-loaded routes and async data boundaries.
- **Next.js `<Image />`** for all image assets — never raw `<img>` tags in Next.js projects.
- **Code splitting:** Use dynamic `import()` for heavy feature modules. Keep the initial bundle small.
- **Minimize dependencies:** Prefer native browser/runtime APIs over adding a package. Every new dependency is a potential attack surface and a bundle-size cost.
- **Python:** Lazy-load ML models. Use generator functions for large data pipelines instead of loading everything into memory.

### CorrelationId
Every request, job, or user-initiated action must carry a **CorrelationId** — a 7-character alphanumeric string beginning with lowercase `c` (e.g., `c1a2b3d`). It must be:
- Attached to all log entries for the lifetime of the request.
- Included in API error responses so support can trace issues.
- Generated at the entry point (API route handler, button click handler, task scheduler).

```typescript
// TypeScript (Node.js built-in crypto module)
import { randomBytes } from "crypto";
const correlationId = "c" + randomBytes(3).toString("hex"); // e.g. "c3f9a1b"
```
```python
# Python — use secrets for cryptographically secure generation
import secrets, string
_alphabet = string.ascii_lowercase + string.digits
correlation_id = "c" + "".join(secrets.choice(_alphabet) for _ in range(6))
```

### Error Handling
- **TypeScript / Node.js:** Centralized error-boundary pattern for React. At the API level, always return structured JSON errors (`{ error: string, correlationId: string }`). Never expose stack traces to clients.
- **User feedback:** Surface errors to the user via a Toast component — never silently swallow errors or only log them.
- **Python:** Catch specific exception types rather than bare `except Exception`. Log with the CorrelationId, then re-raise or handle gracefully.
- **C#:** Return typed `Result<T>` or use custom error models rather than throwing generic exceptions across service boundaries.

### Internationalization (i18n)
- All user-visible strings in web projects must go through `react-i18next`. No hardcoded English strings in JSX.
- Provide at minimum English (`en`) and French (`fr`) translations.
- Use nested JSON keys: `"products.card.addToCart"`, not flat keys.

---

## 🕊️ Privacy Principles

- **Data minimization:** Collect only what we need, for the shortest time we can. If a feature works without personal data, don’t collect it.
- **No hidden tracking:** Do not add fingerprinting, cross-site tracking, or “silent” analytics. If we measure something, make it clear and make it optional when possible.
- **Local-first when practical:** Prefer on-device/local storage and processing where it meets the user’s needs.
- **Keep PII out of logs:** Logs are for debugging, not for storing personal data. Redact or avoid sensitive fields.
- **User control:** Make it easy to view, export, and delete personal data. Defaults should protect the user even if they never touch settings.

## 🔒 Security Principles

- **Privacy reminder:** Security is necessary, but it is not the same thing as privacy. Always pressure-test “security requirements” to ensure they do not introduce unnecessary tracking, data collection, or surveillance.

- **OWASP Top 10 compliance:** Treat every endpoint as adversarial. Validate, sanitize, and authorize before processing.
- **Input validation:** All user inputs must pass a Zod schema (TypeScript) or a validated model (Python/C#) before touching business logic.
- **SQL injection prevention:** Use parameterized queries exclusively. No string concatenation in SQL. Ever.
- **Authentication:** Passwords hashed with `bcryptjs` (Node) or `bcrypt` (Python). JWT tokens expire in 24 hours; verify signature on every protected route.
- **Secrets:** Use GCP Secret Manager. Never commit `.env` files. Add `.env*` to `.gitignore`. Document required variables in `.env.example` with placeholder values only.
- **Minimalist footprint:** Zero-dependency policy for non-essential features. Every third-party package must justify its inclusion.
- **Row-Level Security (RLS):** Enforce user-scoped data access at the query level (filter by `user_id` from the authenticated JWT). Design for RLS even when using managed PostgreSQL.
- **Extension security (Chrome extensions):** Declare only the minimum required permissions in `manifest.json`. Never request `<all_urls>` unless strictly necessary.

---

## 🛠️ Getting Started

### All Projects
```bash
git fetch
git pull
```

### Node.js / Next.js Projects
```bash
npm install
cp .env.example .env.local  # Fill in your environment variables
npm run build && npm run start
```

For development with hot-reload:
```bash
npm run dev
```

### Python Projects
```bash
python -m venv .venv
# Windows
.\.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
python main_app.py
```

**CLI wrapper (Windows):** Create `your-project.cmd` next to `your-project.py`:
```cmd
@echo off
python "%~dp0your-project.py" %*
```
Add the folder containing the `.cmd` file to your `PATH`. Then run:
```powershell
your-project your-command your-argument --your-flags
```

### C# / WinUI 3 Projects
```bash
dotnet restore
dotnet build
dotnet run
```
For production packaging:
```bash
dotnet publish -c Release
```

---
- **Authentication:** Passwords hashed with `bcryptjs` (Node) or `bcrypt` (Python). JWT tokens expire in 24 hours; verify signature on every protected route.
- **Secrets:** Use GCP Secret Manager. Never commit `.env` files. Add `.env*` to `.gitignore`. Document required variables in `.env.example` with placeholder values only.
- **Minimalist footprint:** Zero-dependency policy for non-essential features. Every third-party package must justify its inclusion.
- **Row-Level Security (RLS):** Enforce user-scoped data access at the query level (filter by `user_id` from the authenticated JWT). Design for RLS even when using managed PostgreSQL.
- **Extension security (Chrome extensions):** Declare only the minimum required permissions in `manifest.json`. Never request `<all_urls>` unless strictly necessary.

---

## 🛠️ Getting Started

### All Projects
```bash
git fetch
git pull
```

### Node.js / Next.js Projects
```bash
npm install
cp .env.example .env.local  # Fill in your environment variables
npm run build && npm run start
```

For development with hot-reload:
```bash
npm run dev
```

### Python Projects
```bash
python -m venv .venv
# Windows
.\.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
python main_app.py
```

**CLI wrapper (Windows):** Create `your-project.cmd` next to `your-project.py`:
```cmd
@echo off
python "%~dp0your-project.py" %*
```
Add the folder containing the `.cmd` file to your `PATH`. Then run:
```powershell
your-project your-command your-argument --your-flags
```

### C# / WinUI 3 Projects
```bash
dotnet restore
dotnet build
dotnet run
```
For production packaging:
```bash
dotnet publish -c Release
```

---

## 📋 Code Review Checklist

Before opening a PR, confirm all applicable items:

- [ ] Always branch from `main` (or the primary branch) at the start of a task
- [ ] No `any` types; all inputs and API responses are Zod-validated (TypeScript)
- [ ] No hardcoded secrets or credentials anywhere in the diff
- [ ] No personal data in logs or analytics by default; telemetry is opt-in and documented when used
- [ ] No new tracking/fingerprinting introduced (including “anonymous” identifiers that can be linked back to a person)
- [ ] SQL queries use parameterized syntax — no string interpolation
- [ ] CorrelationId generated and propagated through logs and error responses
- [ ] Create a PR at the end of every task for human review (never merge directly to main)
- [ ] All user-visible strings are externalized via i18n (web projects)
- [ ] New UI elements reuse existing Shadcn / `@/components/ui` primitives where possible
- [ ] `console.log`, `print()`, debug statements removed
- [ ] Unused imports removed
- [ ] `.env` and secret files are gitignored
- [ ] Error paths return user-friendly Toast notifications (not silent failures)
- [ ] Python virtual environment not committed (`.venv/` in `.gitignore`)
- [ ] C# nullable annotations enabled; no null dereference warnings

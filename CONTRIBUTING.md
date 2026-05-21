# Contributing to VaultWares

Welcome! All VaultWares contributions — whether from Copilot, Gemini Code Assist, or a human developer — must meet the quality, security, and consistency bar described here. Read this document before writing or reviewing any code.

---

## 🏗️ Starting a New Repository

Always bootstrap from the `vaultwares-template` repository. This ensures you start with the correct folder layout, `.github` guidelines, `.gitignore`, and base configuration.

```bash
# Use GitHub's "Use this template" button, or:
gh repo create my-new-project --template p-potvin/vaultwares-template
```

---

## 🗂️ Folder Structure

Follow these conventions for each project type. Do not deviate without a documented reason.

### Web / Next.js / React
```
src/
├── app/                   # Next.js App Router (pages, layouts, API routes)
├── components/
│   ├── ui/                # Atomic Shadcn/Radix primitives — do NOT modify directly
│   └── features/          # Feature-scoped components (e.g. /cart, /checkout, /auth)
├── hooks/                 # Custom React hooks (camelCase, must start with `use`)
├── lib/                   # Utilities, Zod schemas, API clients, shared logic
├── types/                 # Global TypeScript interfaces and type aliases
├── store/                 # Zustand stores or React Context providers
└── styles/                # Global CSS, Tailwind theme overrides
```

### Python Desktop / CLI
```
project-root/
├── main_app.py            # Entry point
├── module_name/           # Feature module folders (snake_case)
├── vault_sync.py          # Vault sync utility (if applicable)
├── requirements.txt
└── .venv/                 # Local venv — never committed
```

### C# WinUI 3
```
ProjectName/
├── Models/                # Data classes
├── Services/              # Business logic (interface + implementation)
├── ViewModels/            # MVVM layer (CommunityToolkit.Mvvm)
├── Views/                 # XAML files
├── Converters/            # XAML value converters
└── Themes/                # XAML resource dictionaries for light/dark themes
```

---

## ✍️ Coding Standards

### TypeScript
1. **Strict mode is non-negotiable.** `"strict": true` must be set in `tsconfig.json`.
2. **No `any`.** Use `unknown` + type guards or Zod schemas for dynamic data.
3. **`interface` for object shapes; `type` for unions, primitives, and mapped types.**
4. **Named exports only** on components and hooks — no default exports on components.
5. **Functional components with arrow syntax:**
   ```tsx
   export const CheckoutButton = ({ label, onClick }: CheckoutButtonProps) => {
       return <button onClick={onClick}>{label}</button>;
   };
   ```
6. **Server Components by default.** Add `"use client"` only when you need browser events or React hooks.
7. **Validate all inputs with Zod before touching business logic:**
   ```typescript
   const result = createOrderSchema.safeParse(req.body);
   if (!result.success) {
       return res.status(400).json({ error: "Invalid payload", details: result.error.errors });
   }
   ```
8. **Parameterized SQL queries only:**
   ```typescript
   // ✅ correct
   await pool.query("SELECT * FROM orders WHERE user_id = $1", [userId]);
   // ❌ never
   await pool.query(`SELECT * FROM orders WHERE user_id = '${userId}'`);
   ```
9. **Wrap multi-step writes in database transactions** (`BEGIN` / `COMMIT` / `ROLLBACK`).
10. **Mock fallback in development:** If the database is unavailable, return mock data rather than crashing. Gate on `isDbConnected()`.

### Python
1. **Always activate `.venv`** before running `pip` or `python`. Never install to the global environment.
2. **Type hints on all public functions and class attributes.**
3. **Thread safety:** Protect shared mutable state with `threading.Lock()`. Use daemon threads for background workers.
4. **Lazy-load heavy models** (ML, audio) on first use to keep startup fast.
5. **Use the `logging` module** — never `print()` for application output. Use rotating file handlers.
6. **Catch specific exceptions** — avoid bare `except Exception`.

### C#
1. **MVVM strictly enforced.** No business logic in `.xaml.cs` code-behind files.
2. **`#nullable enable`** at the top of every `.cs` file.
3. **Private fields use `_camelCase`** prefix.
4. **Define `IService` interfaces** for all services to enable dependency injection and testability.
5. **Async/await throughout.** Never block the UI thread with `.Result` or `.Wait()`.

---

## 📛 Naming Conventions

### TypeScript
| Element | Convention | Example |
|---|---|---|
| Components | PascalCase | `ProductVault.tsx` |
| Hooks | camelCase + `use` prefix | `useVaultAuth.ts` |
| Utilities | kebab-case | `format-currency.ts` |
| Interfaces / Types | PascalCase | `CartContextType` |
| Constants | UPPER_SNAKE_CASE | `MAX_RETRY_COUNT` |
| Zod schemas | camelCase + `Schema` suffix | `createOrderSchema` |

### Python
| Element | Convention | Example |
|---|---|---|
| Classes | PascalCase | `RealTimeSTTApp` |
| Functions / methods | snake_case | `get_speech_prob()` |
| Private methods | `_snake_case` | `_processing_loop()` |
| Files | snake_case | `audio_capture.py` |
| Constants | UPPER_SNAKE_CASE | `MAX_SILENCE_CHUNKS` |

### C#
| Element | Convention | Example |
|---|---|---|
| Classes / Interfaces | PascalCase | `BackupService`, `IBackupService` |
| Properties / Public methods | PascalCase | `ExecuteBackupAsync()` |
| Private fields | `_camelCase` | `_backupJobs` |
| Local variables | camelCase | `backupResult` |

---

## 🛡️ Security Checklist

Run through this list before submitting any PR. Every item must be answered.

### Secrets & Credentials
- [ ] No secrets, API keys, or credentials are present anywhere in the diff.
- [ ] `.env` and `.env.local` are listed in `.gitignore`.
- [ ] A `.env.example` file exists with placeholder values documenting each required variable.
- [ ] Sensitive values at runtime are sourced from **GCP Secret Manager**, not environment files in production.

### Input Validation & SQL
- [ ] All user-supplied or external data passes a Zod schema (TypeScript) or equivalent validation before use.
- [ ] Every SQL query uses **parameterized syntax** (`$1`, `$2`, …). No string interpolation in SQL.
- [ ] Multi-step writes are wrapped in a database transaction with rollback on error.

### Authentication & Authorization
- [ ] Protected routes/endpoints verify the JWT signature and check expiry on every request.
- [ ] Data queries filter by `user_id` derived from the authenticated token — not from a client-supplied parameter.
- [ ] Passwords are hashed with `bcryptjs` (Node) or `bcrypt` (Python) — never stored plain or with MD5/SHA1.

### Error Handling & Logging
- [ ] Errors surface to the user as Toast notifications — no silent failures.
- [ ] Stack traces and internal error details are **not** exposed in API responses.
- [ ] A **CorrelationId** (`c` + 6 alphanumeric characters, e.g., `c3f9a1b`) is generated at the entry point and included in all log entries and error responses for the duration of the request.

### Browser Extensions (Chrome)
- [ ] `manifest.json` requests only the minimum required permissions.
- [ ] `<all_urls>` host permission is not requested unless strictly necessary and documented.

### General
- [ ] No new dependencies added without a clear justification. Prefer native APIs.
- [ ] Python: `.venv/` directory is not committed.
- [ ] C#: `#nullable enable` is present; no nullable dereference warnings.

---

## 🔁 Pull Request Process

1. **Branch:** Create a feature branch from `main` (`feat/your-feature` or `fix/issue-slug`).
2. **Scope:** Keep PRs focused. One logical change per PR.
3. **Self-review:** Run the security checklist above before requesting review.
4. **Lint & test:** Run the project's lint and test commands and ensure they pass.
5. **Description:** Describe *what* changed, *why*, and any *migration steps* if applicable.
6. **Labels:** Apply relevant GitHub labels (`enhancement`, `bug`, `security`, etc.).
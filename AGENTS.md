## Project Specific Instructions

1. Always use the conda env agenda for this project.
2. Do not perform any destructive actions on the AZURE REMOTE PG DB. Develop locally, and sync local to remote new data thereafter.
3. Include .md files in docs folder, unless asked differently. Refer important docs in the main README.md in the project root.
4. Code decoupled from the main app/API should be placed in the scripts folder.
5.  Always keep an updated requirements.txt file in the project root.
6. The local database, inside the running Docker container, is named "agenda_db", if it already exists. If not, use this name when we create it.
7. Modularize the code, following software development best practices.
8. Always externalize server parametrization in .env. Also, always check .env for server and DB parameters.
9. Do not use emojis. Prefer professional icons / .svg, like we have in other projects.
10. Always get inspiration and reuse code/modules/functions of other projects pointed in this workspace (without modifying those other projects).
11. We are building cutting-edge platforms, inspired by leading platforms like Palantir and Hexagon.
12. Favor **optimistic UI** patterns: show the expected result to the user immediately, then reconcile on server response. Roll back gracefully on failure. Avoid unnecessary spinners and loading states for user-initiated actions — users should feel the system is instantaneous whenever it is possible. This applies to builds, deletes, moves, and any CRUD operation where the happy path is the norm.


## General Instructions

### Think Before Coding
Don't assume. Don't hide confusion. Surface tradeoffs.

Before implementing:

- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### Simplicity First
Minimum code that solves the problem. Nothing speculative.

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.
- Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### Surgical Changes
Touch only what you must. Clean up only your own mess.

When editing existing code:

- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it — don't delete it.

When your changes create orphans:

- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.
- The test: Every changed line should trace directly to the user's request.

### Goal-Driven Execution
Define success criteria. Loop until verified.

Transform tasks into verifiable goals:

- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:

1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]

### Step-by-Step Execution
Always split implementations into small, incremental steps. Never attempt to write an entire feature or document in a single pass.

- Break every task into a todo list of small, verifiable steps. Complete one step at a time.
- For code: implement one module, function, or logical unit per step. Verify it before moving to the next.
- For documents (.md files): write one section at a time. Never generate the entire document in a single response — create the file with the first section, then append subsequent sections one by one.
- This avoids "response too long" errors and ensures each step is correct before building on top of it.
- If a step is too large to complete in one pass, split it further. When in doubt, split.


## Code Patterns

### YAGNI and DRY
- **YAGNI**: Don't build for hypothetical future requirements. If it's not needed *now*, don't write it.
- **DRY with a rule of three**: Tolerate duplication once, extract on the third occurrence — never on the first.

### Structural Rules
- Prefer guard clauses / early returns over deep nesting. Max 3 levels of indentation.
- Functions do one thing. If you need "and" in the function name, split it.
- Name by *what* and *why*, not *how*. `get_active_tenants()` not `query_db_filter_status()`.
- Prefer composition over inheritance. Prefer flat module structure over deep package hierarchies.
- If a library solves it, use the library. Don't hand-roll what's already tested and maintained.

### Code Style and Conventions
- **Python**: PEP 8, type hints on all public function signatures, docstrings on public APIs.
- **JavaScript/Frontend**: Consistent with existing files. `camelCase` for variables, `PascalCase` for classes.
- [project specific] **Error responses**: Use the project's `error_codes.py` / `error_responses.py` — never invent ad-hoc error strings.


## Security Measures

### Never Trust User Input
- Validate and sanitize every API input. Use Pydantic models for request schemas.
- Never pass raw user input to SQL — always use parameterized queries / ORM methods.
- Never render unescaped user content in HTML (XSS prevention).

### Authentication and Authorization (RBAC)
- Every endpoint must have an explicit role check. No endpoint is "open by default."
- Principle of least privilege: grant the minimum role needed, never admin "for convenience."
- Tenant isolation: every data query must be scoped to the authenticated tenant. Never assume tenant from the request body — derive from the session/token.

### Secrets Management
- All secrets in .env. Never hardcode, never commit .env to git.
- Never log tokens, passwords, or PII. Redact before logging.
- Rotate secrets on a schedule; never share credentials between environments.

### OWASP Top 10 Awareness
- Design and review against the OWASP Top 10. Before merging a new endpoint, ask: "Which OWASP risks does this introduce, and how are they mitigated?"
- Key focus areas: injection, broken auth, sensitive data exposure, broken access control, CSRF, XSS.

### API Hardening
- Rate-limit auth and write endpoints.
- CSRF protection on all state-changing operations.
- Security headers on all responses (CSP, HSTS, X-Frame-Options, etc.).
- Return generic error messages to clients; log detailed errors server-side only. Never leak stack traces or internal state to the client.

### Audit and Accountability
- Log all state-changing operations with: who, what, when, from-where.
- Impersonation actions must be explicitly logged and reversible.


## Testing Standards

- Write tests alongside features, not after. A feature is not done until it has tests.
- Test naming: `test_<unit>_<scenario>_<expected_result>`.
- Test the happy path first, then edge cases, then error paths.
- Never test implementation details — test behavior and contracts.
- Integration tests for API endpoints; unit tests for business logic.


## API Design Conventions

- RESTful resource naming: plural nouns (`/tenants`, `/users`, `/reports`).
- Consistent response envelope: `{ "data": ..., "error": null }` or use the project's existing format.
- HTTP status codes: 200 success, 201 create, 204 delete, 400 client error, 401 unauth, 403 forbidden, 404 not found, 409 conflict, 500 server error.
- Pagination on list endpoints. Never return unbounded collections.


## Dependency Management

- Pin all versions in requirements.txt. No unpinned ranges.
- Before adding a new dependency: justify why existing deps can't solve it. Every dep is attack surface.
- Review transitive dependencies for known vulnerabilities (pip-audit / safety).
- Never install packages at runtime. All deps must be in requirements.txt and installed at build time.


## Error Handling Patterns

- [project specific] Use the project's `error_codes.py` for all error responses. No ad-hoc error strings.
- Fail fast: validate early, return early. Don't bury validation deep in the call stack.
- Log the full context server-side; return a generic, safe message to the client.
- Never swallow exceptions silently. If you catch, you must either handle, re-raise, or log — never all three absent.


---

When in doubt, ask.
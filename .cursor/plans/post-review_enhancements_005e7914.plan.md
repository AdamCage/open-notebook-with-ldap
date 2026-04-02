---
name: Post-Review Enhancements
overview: "Four enhancements: externalize LDAP config from docker-compose.yml to .env via interpolation, update README.md with LDAP documentation, create C4/sequence architecture diagrams in PlantUML under docs/8-ARCHITECTURE, and create 5 project-specific Cursor skills."
todos:
  - id: docker-env
    content: "Externalize LDAP config: update docker-compose.yml with ${VAR:-default} interpolation, add LDAP section to .env.example"
    status: completed
  - id: readme-update
    content: "Update README.md: add LDAP features, enterprise auth section, update comparison table and roadmap"
    status: completed
  - id: arch-c4-diagrams
    content: Create docs/8-ARCHITECTURE/ with C4 PlantUML diagrams (context, containers, component-api, component-frontend, code-domain)
    status: completed
  - id: arch-seq-diagrams
    content: Create sequence diagrams in docs/8-ARCHITECTURE/ (password-auth, ldap-auth, source-ingestion, chat, ask, podcast, owner-scoping)
    status: completed
  - id: arch-index
    content: Create docs/8-ARCHITECTURE/index.md hub page linking all diagrams
    status: completed
  - id: skill-ldap
    content: Create .cursor/skills/ldap-module/SKILL.md
    status: completed
  - id: skill-surrealdb
    content: Create .cursor/skills/surrealdb-migrations/SKILL.md
    status: completed
  - id: skill-langgraph
    content: Create .cursor/skills/langgraph-workflows/SKILL.md
    status: completed
  - id: skill-api
    content: Create .cursor/skills/api-endpoint-creation/SKILL.md
    status: completed
  - id: skill-frontend
    content: Create .cursor/skills/frontend-patterns/SKILL.md
    status: completed
isProject: false
---

# Post-Review Enhancements

Agents from `.cursor/rules`: `backend-architect`, `software-architect`, `security-engineer`, `frontend-developer`, `technical-writer`, `devops-automator`.

---

## 1. Docker-Compose: LDAP Config via .env Interpolation

**Problem:** LDAP env vars are hardcoded (commented out) in [docker-compose.yml](docker-compose.yml). Should use `${VAR:-default}` interpolation so users configure via `.env`.

**Changes:**

- **[docker-compose.yml](docker-compose.yml):** Replace commented-out LDAP env vars with `${VAR:-default}` interpolation in the `open_notebook` service. Keep existing non-LDAP vars as-is. Add LDAP block:

```yaml
# LDAP Authentication (configure in .env)
- ENABLE_LDAP=${ENABLE_LDAP:-false}
- LDAP_SERVER_HOST=${LDAP_SERVER_HOST:-localhost}
- LDAP_SERVER_PORT=${LDAP_SERVER_PORT:-389}
- LDAP_USE_TLS=${LDAP_USE_TLS:-true}
- LDAP_VALIDATE_CERT=${LDAP_VALIDATE_CERT:-true}
- LDAP_CA_CERT_FILE=${LDAP_CA_CERT_FILE:-}
- LDAP_CIPHERS=${LDAP_CIPHERS:-ALL}
- LDAP_ATTRIBUTE_FOR_USERNAME=${LDAP_ATTRIBUTE_FOR_USERNAME:-uid}
- LDAP_ATTRIBUTE_FOR_MAIL=${LDAP_ATTRIBUTE_FOR_MAIL:-mail}
- LDAP_APP_DN=${LDAP_APP_DN:-}
- LDAP_APP_PASSWORD=${LDAP_APP_PASSWORD:-}
- LDAP_SEARCH_BASE=${LDAP_SEARCH_BASE:-}
- LDAP_SEARCH_FILTERS=${LDAP_SEARCH_FILTERS:-}
- LDAP_JWT_SECRET=${LDAP_JWT_SECRET:-}
```

- **[.env.example](.env.example):** Add a new `LDAP Authentication` section with all LDAP vars (commented out, with descriptions). This is where users will copy and customize.

---

## 2. Update README.md

**Problem:** [README.md](README.md) has no mention of LDAP authentication, per-user data isolation, or the new security model.

**Changes to [README.md](README.md):**

- Add "LDAP Authentication" to the **Key Features** section (both table and feature list)
- Add a new section **"Enterprise Authentication (LDAP)"** after Quick Start, with:
  - Brief description of LDAP support
  - Quick config steps (copy .env, set ENABLE_LDAP=true, configure server)
  - Link to [docs/5-CONFIGURATION/security.md](docs/5-CONFIGURATION/security.md)
- Update the comparison table to add "LDAP/Enterprise Auth" row (Open Notebook: LDAP + password; Google: Google account only)
- Update "Recently Completed" roadmap section to include LDAP auth and per-user data isolation
- Update the feature list badge/line about auth: from "Optional Password Protection" to "LDAP + Password Authentication"

---

## 3. Architecture Documentation (PlantUML C4 + Sequence Diagrams)

**New directory:** `docs/8-ARCHITECTURE/`

Create an `index.md` hub plus individual `.puml` files. All diagrams use PlantUML with the C4-PlantUML library (`!include https://raw.githubusercontent.com/plantuml-stdlib/C4-PlantUML/master/C4_*.puml`).

### C4 Diagrams

- `**c4-context.puml`** -- System Context: Open Notebook system boundary, external actors (User, LDAP Server, AI Providers), and external systems
- `**c4-containers.puml`** -- Container diagram: Frontend (Next.js), API (FastAPI), Database (SurrealDB), Job Queue (Surreal-Commands), showing ports and protocols
- `**c4-component-api.puml`** -- Component diagram for the API container: Routers, Services, Middleware (auth), Domain Models, LangGraph Graphs, AI Provisioning (Esperanto), Database layer
- `**c4-component-frontend.puml`** -- Component diagram for the Frontend: Pages (App Router), Components (Shadcn/ui), Stores (Zustand), Hooks, API Client (Axios/fetch), i18n
- `**c4-code-domain.puml**` -- Code-level diagram: ObjectModel hierarchy (Notebook, Source, Note, ChatSession, PodcastEpisode, etc.), key relationships, owner field

### Sequence Diagrams

- `**seq-password-auth.puml**` -- Password authentication flow (login -> middleware -> bearer check)
- `**seq-ldap-auth.puml**` -- LDAP authentication flow (login form -> POST /auth/ldap -> TLS -> app bind -> search -> user bind -> JWT -> middleware)
- `**seq-source-ingestion.puml**` -- Source processing: upload -> API -> async command -> source_graph (extract -> embed -> transform) -> save
- `**seq-chat.puml**` -- Chat flow: user message -> API -> chat_graph (context build -> LLM call -> stream response) -> save
- `**seq-ask.puml**` -- Ask flow: question -> API -> ask_graph (strategy -> parallel vector_search -> provide_answer -> final_answer) -> stream SSE
- `**seq-podcast.puml**` -- Podcast generation: request -> API -> PodcastService -> surreal-commands -> podcast_creator -> save episode
- `**seq-owner-scoping.puml**` -- Data isolation flow: request -> middleware (extract user identity) -> router (get_owner_id) -> ObjectModel (owner filter) -> SurrealDB (WHERE owner)

### Index File

- `**index.md**` -- Hub page with descriptions of each diagram, rendering instructions (PlantUML server/CLI/VS Code extension), and links to all `.puml` files

---

## 4. Cursor Skills

**New directory:** `.cursor/skills/` (project-level, shared with the repo)

### Skill 1: `ldap-module/SKILL.md`

LDAP authentication module development. Covers the full auth chain (ldap_config.py -> auth.py middleware -> routers/auth.py -> frontend auth-store -> LoginForm). Trigger: working with LDAP, authentication, JWT, or login flows.

### Skill 2: `surrealdb-migrations/SKILL.md`

Creating and managing SurrealDB migrations. Covers: file naming convention (NNN.surrealql / NNN_down.surrealql), registering in async_migrate.py, SurrealQL patterns for fields/indexes/functions, testing via API restart. Trigger: database schema changes, new fields, new tables.

### Skill 3: `langgraph-workflows/SKILL.md`

Creating and modifying LangGraph workflows. Covers: StateGraph pattern, node functions (async), conditional edges, Send for fan-out, configurable dict for context passing, provision_langchain_model, error handling with classify_error, streaming via astream. Trigger: new AI workflows, graph modifications.

### Skill 4: `api-endpoint-creation/SKILL.md`

Creating new FastAPI endpoints following project patterns. Covers: router structure, Pydantic models, service layer, owner scoping (get_current_user + get_owner_id), error handling with custom exceptions, registering in main.py. Trigger: new API routes, new CRUD operations.

### Skill 5: `frontend-patterns/SKILL.md`

Frontend development patterns for the Next.js/React/TypeScript UI. Covers: Zustand stores, TanStack Query hooks, Shadcn/ui components, i18n (all locale files), API client (Axios interceptors), auth integration. Trigger: new UI features, components, or pages.

---

## Files Summary

**Modified:**

- `docker-compose.yml` -- interpolation for LDAP vars
- `.env.example` -- add LDAP section
- `README.md` -- add LDAP documentation

**New:**

- `docs/8-ARCHITECTURE/index.md`
- `docs/8-ARCHITECTURE/c4-context.puml`
- `docs/8-ARCHITECTURE/c4-containers.puml`
- `docs/8-ARCHITECTURE/c4-component-api.puml`
- `docs/8-ARCHITECTURE/c4-component-frontend.puml`
- `docs/8-ARCHITECTURE/c4-code-domain.puml`
- `docs/8-ARCHITECTURE/seq-password-auth.puml`
- `docs/8-ARCHITECTURE/seq-ldap-auth.puml`
- `docs/8-ARCHITECTURE/seq-source-ingestion.puml`
- `docs/8-ARCHITECTURE/seq-chat.puml`
- `docs/8-ARCHITECTURE/seq-ask.puml`
- `docs/8-ARCHITECTURE/seq-podcast.puml`
- `docs/8-ARCHITECTURE/seq-owner-scoping.puml`
- `.cursor/skills/ldap-module/SKILL.md`
- `.cursor/skills/surrealdb-migrations/SKILL.md`
- `.cursor/skills/langgraph-workflows/SKILL.md`
- `.cursor/skills/api-endpoint-creation/SKILL.md`
- `.cursor/skills/frontend-patterns/SKILL.md`


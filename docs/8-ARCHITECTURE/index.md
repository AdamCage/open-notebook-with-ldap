# Architecture Diagrams

This directory contains formal architecture documentation for Open Notebook using [PlantUML](https://plantuml.com/) with the [C4 model](https://c4model.com/) for structural views and UML sequence diagrams for behavioral flows.

## Rendering the Diagrams

All `.puml` files can be rendered with any PlantUML-compatible tool:

- **VS Code**: Install the [PlantUML extension](https://marketplace.visualstudio.com/items?itemName=jebbs.plantuml) and press `Alt+D` to preview.
- **IntelliJ / JetBrains**: Built-in PlantUML support via plugin.
- **CLI**: `java -jar plantuml.jar docs/8-ARCHITECTURE/*.puml` (outputs PNG/SVG).
- **Online**: Paste into [plantuml.com/plantuml](https://www.plantuml.com/plantuml/uml/).
- **Docker**: `docker run --rm -v $(pwd):/data plantuml/plantuml docs/8-ARCHITECTURE/*.puml`

---

## C4 Structural Diagrams

The [C4 model](https://c4model.com/) provides four zoom levels: Context, Containers, Components, and Code.

### Level 1: System Context

**[c4-context.puml](c4-context.puml)** -- Shows Open Notebook as a single system and its relationships with external actors (users, administrators) and external systems (LDAP server, AI providers, content sources).

### Level 2: Container Diagram

**[c4-containers.puml](c4-containers.puml)** -- Decomposes Open Notebook into its runtime containers: the Next.js frontend (port 8502), the FastAPI backend (port 5055), SurrealDB (port 8000), the Surreal-Commands job queue, and the SQLite checkpoint store. Shows protocols and data flows between them.

### Level 3: Component Diagrams

**[c4-component-api.puml](c4-component-api.puml)** -- Zooms into the API server to show its internal components: Auth Middleware, Routers, Services, LDAP Auth module, Domain Models, LangGraph Workflows, AI Provisioning (Esperanto), and the Database Layer.

**[c4-component-frontend.puml](c4-component-frontend.puml)** -- Zooms into the Frontend to show: Pages (App Router), UI Components (Shadcn/ui), State Stores (Zustand), Custom Hooks, API Client (Axios), and the i18n system.

### Level 4: Code Diagram

**[c4-code-domain.puml](c4-code-domain.puml)** -- Class-level view of the domain model hierarchy. Shows `ObjectModel` as the base class with its `owner` field for data isolation, and all subclasses: `Notebook`, `Source`, `Note`, `SourceInsight`, `SourceEmbedding`, `ChatSession`, `PodcastEpisode`. Includes key relationships (`reference`, `artifact`) between models.

---

## Sequence Diagrams

Behavioral flows for all major processes in the system.

### Authentication

**[seq-password-auth.puml](seq-password-auth.puml)** -- Simple password authentication: the frontend sends the password as a Bearer token, the middleware validates it against `OPEN_NOTEBOOK_PASSWORD`, and sets `request.state.user`.

**[seq-ldap-auth.puml](seq-ldap-auth.puml)** -- Full LDAP authentication flow: TLS configuration, application bind, user search with escaped filter, user bind for password verification, JWT token creation, and the i18n error mapping in the frontend.

**[seq-local-auth.puml](seq-local-auth.puml)** -- Local account authentication flow (`AUTH_MODE=local`): user self-registration with pending status, admin approval workflow, bcrypt password verification, JWT session token issuance, and the middleware's cached database status check for active user enforcement.

### Core Workflows

**[seq-source-ingestion.puml](seq-source-ingestion.puml)** -- Async source processing: file upload or URL submission, async command submission via Surreal-Commands, the `source_graph` LangGraph workflow (content extraction, embedding generation, optional transformations), and status polling.

**[seq-chat.puml](seq-chat.puml)** -- Conversational AI chat: context building from selected sources/notes, LLM invocation via Esperanto, streaming response, and checkpoint persistence in SQLite.

**[seq-ask.puml](seq-ask.puml)** -- Multi-step Ask workflow: strategy generation (search terms), parallel vector search fan-out via `Send`, per-search answer synthesis, final answer aggregation, all streamed as SSE events.

**[seq-podcast.puml](seq-podcast.puml)** -- Podcast generation pipeline: profile validation, background command submission, outline/transcript generation via LLM, TTS synthesis for each speaker, audio mixing, and episode record creation with owner scoping.

### Security

**[seq-owner-scoping.puml](seq-owner-scoping.puml)** -- Per-user data isolation pattern: JWT decoding in middleware, owner ID extraction, owner-filtered queries in `ObjectModel.get_all()`, owner-stamped record creation, and defense-in-depth checks in `ObjectModel.get()`.

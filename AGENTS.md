# AGENTS.md

Before writing application code, inspect the existing project and understand its architecture. This is a greenfield repo — no app code exists yet; only the skill collection in `.agents/` (managed via `skills-lock.json`, installed from GitHub). Load relevant skills from `.agents/` as needed.

## Stack

- Frontend: React + TypeScript + Vite
- Styling: Tailwind CSS
- Components: shadcn/ui + Radix
- Animation: Motion
- Backend: Python + FastAPI + Pydantic
- Database: Supabase PostgreSQL
- AI: Gemini API

## Engineering

- Production-grade, maintainable architecture with strong TS/Python typing.
- Reuse existing components and utilities; no duplicate abstractions.
- Keep frontend, API, services, and database concerns separated; no overengineering.
- Proper error handling; validate all external input.
- Security-first: never expose secrets, never put secrets in frontend code, use environment variables.
- Tests required for important business logic. Run linting, type checking, and tests before considering work complete.

## Database

- Do not modify the existing database/schema unless explicitly requested.
- Inspect the existing Supabase schema before proposing changes; use migrations for intentional changes.
- Respect existing RLS policies; never expose the service-role key to the frontend.

## UI/UX

- Minimal, refined, Apple-inspired visual language with strong typography, spacing, and hierarchy.
- Responsive, accessible, keyboard accessible.
- Excellent loading, empty, and error states.
- Use shadcn/ui primitives where appropriate.
- Use Motion only when it improves interaction or communicates state — no meaningless animations.

## Strictly avoid

- Generic AI-generated dashboard aesthetics, excessive rounded cards, excessive gradients, purple/blue AI gradients by default, unnecessary glassmorphism, excessive shadows, decorative animation, huge purposeless hero sections.

## Workflow (substantial features)

1. Inspect existing code.
2. Understand dependencies and architecture.
3. Explain the implementation plan.
4. Implement incrementally.
5. Test.
6. Type-check.
7. Lint.
8. Review the final diff.
9. Check security, performance, and responsive behavior.

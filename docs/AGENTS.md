# Repository Guidelines

## Project Structure & Module Organization
`backend/` contains FastAPI services in `app/` (API routes, services, memory, models) with tests in `tests/` and migrations in `alembic/`. The desktop client lives in `desktop/`, where Vite+React code sits in `src/` alongside TypeScript and Tailwind configs. Documentation resides in `docs/`, and `infra/docker-compose.yml` provides local PostgreSQL and Redis when required.

## Build, Test, and Development Commands
Backend setup: `cd backend && python -m venv venv && source venv/bin/activate && pip install -r requirements.txt`. Start the API with `uvicorn app.main:app --reload`. Run quality gates using `pytest tests/ -v --cov=app`. For the desktop app, run `cd desktop && npm install`, use `npm run dev` for hot reload, and ship bundles with `npm run build`. Bring up shared services via `docker compose -f infra/docker-compose.yml up`.

## Coding Style & Naming Conventions
Format Python code with `black app/` and `isort app/`; lint using `flake8 app/` and `mypy app/`. Keep modules `snake_case`, classes `PascalCase`, and constants `UPPER_SNAKE`. Frontend code relies on ESLint and Prettier—run `npm run lint` and `npm run format`; React components use `PascalCase.tsx` and hooks `useCamelCase.ts`. Exclude generated assets and secrets from commits.

## Testing Guidelines
Mirror backend modules with `test_*.py` files and centralize fixtures in `tests/conftest.py`. Target at least 80% coverage before submitting (`pytest --cov`). Desktop features should include component or hook specs (Vitest or similar) stored beside their sources as `*.test.tsx`. Document every executed command in the PR template’s testing section.

## Commit & Pull Request Guidelines
Follow conventional commits as seen in history (`feat(memory):`, `docs:`, `fix:`) and keep subjects under ~72 characters. Group coherent changes into a single commit and explain behavioral shifts in the body. Pull requests must complete `PR_TEMPLATE.md`: provide a narrative, mark relevant change types, link issues (`Closes #123`), attach visuals for UI updates, and confirm that linting, formatting, and tests succeeded.

## Configuration & Security Tips
Copy `backend/.env.example` to `.env` and populate Google OAuth, LangFuse, and LLM keys without committing credentials. Prefer OS-level secret storage over plaintext files. Recreate containers with `docker compose -f infra/docker-compose.yml down && docker compose -f infra/docker-compose.yml up --build` after configuration changes. Review `docs/ARCHITECTURE.md` before altering core agent flows so backend and desktop expectations stay aligned.

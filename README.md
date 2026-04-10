# feishu-incident-copilot

This workspace now contains the minimum runnable scaffold for P0.

## What P0 needs

P0 does not require Redis, PostgreSQL, or Docker yet. The current goal is a local FastAPI service that can later receive Feishu callbacks, load thread context, retrieve local knowledge, and return a structured summary.

## Local setup

Windows PowerShell:

```powershell
.\scripts\bootstrap.ps1
```

That script will:

- install Python 3.11 through `uv` if needed
- create `.env` from `.env.example` if it is missing
- create or update the virtual environment
- install runtime and test dependencies

## Run the app

```powershell
.\scripts\dev.ps1
```

The service will start on [http://127.0.0.1:8000](http://127.0.0.1:8000).

## Run tests

```powershell
.\scripts\test.ps1
```

## Environment variables

The scaffold reads configuration from `.env`. Replace the placeholder values before wiring real Feishu or LLM integrations.

## Project layout

The module layout follows `tech-spec.md`:

- `app/api`: inbound routes
- `app/clients`: external service clients
- `app/core`: configuration and logging
- `app/models`: shared contracts
- `app/prompts`: prompt templates
- `app/services`: orchestration services
- `tests`: smoke and contract tests
- `data/knowledge`: local knowledge documents

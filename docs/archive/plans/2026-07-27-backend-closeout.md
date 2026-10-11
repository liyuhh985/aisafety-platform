> 状态：implemented
> 最后核对：2026-10-09
> 历史文档：当前版本请以 docs/current/ 和代码为准。

# Backend Closeout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the confirmed backend closeout gaps by making Java AI health reflect Python AI availability, keeping Redis cache failures out of the business path, bounding image decoding work, and verifying the existing report/SSE path without expanding V1 scope.

**Architecture:** Keep the existing Java `AiController` -> `AiService` -> Python FastAPI `/api/ai/health` path. The controller will return success only when the existing client health probe succeeds; Python health remains a local readiness response and does not expose credentials or model responses.

**Tech Stack:** Java 21, Spring Boot 3.3.5, Spring MVC, RestTemplate, JUnit 5, Maven; Python 3, FastAPI, unittest.

## Global Constraints

- Preserve all existing user worktree changes.
- Do not add business modules, MQ, Docker, new agents, or redesign JWT.
- Do not write real API keys, tokens, passwords, `.env`, or local credentials to tracked files or documentation.
- Keep the existing report ownership filters and Python image/SSE cleanup behavior intact.
- Treat Redis as an optional cache: database reads and successful writes must not fail only because cache I/O is unavailable.
- Reject images above the configured decoded-pixel limit before conversion.

---

### Task 1: Make Java AI Health Accurate

**Files:**
- Modify: `safety-web/src/main/java/com/safety/web/controller/AiController.java`
- Test: `safety-web/src/test/java/com/safety/web/controller/AiControllerHealthTest.java`
- Modify: `safety-web/pom.xml` only if the existing build has no test dependency.

**Interfaces:**
- Consumes: `AiService.isHealthy()`.
- Produces: `GET /api/ai/health` returns the existing `R` envelope with success only when Python health is reachable; unavailable Python returns a failure envelope.

- [ ] **Step 1: Write the failing tests**

  Cover both `AiService.isHealthy() == true` and `false`; assert the response code is `200` only for the healthy case and is not `200` for the unavailable case.

- [ ] **Step 2: Run the focused test and verify it fails**

  Run: `mvn -pl safety-web -am -Dtest=AiControllerHealthTest test`
  Expected: the unavailable-service test fails because the current controller always returns `ok`.

- [ ] **Step 3: Implement the minimal controller change**

  Delegate to `AiService.isHealthy()`, return the existing success response for a healthy service, and return a concise non-sensitive failure response otherwise.

- [ ] **Step 4: Run the focused test and verify it passes**

  Run: `mvn -pl safety-web -am -Dtest=AiControllerHealthTest test`
  Expected: both health tests pass.

- [ ] **Step 5: Run regression verification**

  Run Python `python -m unittest discover -s . -p 'test*.py' -v` in `ai-module` and Java `mvn -pl safety-web -am test`.
  Expected: all existing tests and the new health tests pass.

### Task 2: Verify the Existing Closeout Contract

**Files:**
- Inspect only: `ai-module/server.py`, `ai-module/core/orchestrator.py`, `safety-web/src/main/java/com/safety/web/service/AiService.java`, report/security classes, and `docs/backend-closeout-task.md`.

**Interfaces:**
- Consumes: existing local Python and Java services.
- Produces: recorded HTTP status/results for Python health, Java health, Python SSE error termination, and Maven compilation.

- [ ] **Step 1: Run Python unit and syntax checks.**
- [ ] **Step 2: Run Python `/api/ai/health` and confirm no sensitive output.**
- [ ] **Step 3: Run Maven compile/test using the bundled Maven binary.**
- [ ] **Step 4: Record any unavailable MySQL/Redis/MinIO or real-account checks as verification gaps instead of changing configuration.**

### Task 3: Harden Cache and Image Boundaries

**Files:**
- Modify: `safety-service/src/main/java/com/safety/service/service/impl/HazardServiceImpl.java`
- Test: `safety-service/src/test/java/com/safety/service/service/impl/HazardServiceImplCacheTest.java`
- Modify: `ai-module/config.py`
- Modify: `ai-module/server.py`
- Test: `ai-module/test_server_upload_validation.py`
- Modify: `.claude/settings.local.json` to remove tracked credential-bearing commands.

- [ ] **Step 1: Reproduce Redis read and invalidation failures with unit tests.**
- [ ] **Step 2: Catch cache runtime failures, log them, and continue through database/business results.**
- [ ] **Step 3: Reproduce a small compressed image with excessive decoded pixels.**
- [ ] **Step 4: Reject excessive pixels before conversion and map decoder bomb errors to 413.**
- [ ] **Step 5: Scan tracked settings and diff for credential patterns, then run the full regression suite.**

### Task 4: Review and Handoff

**Files:**
- Inspect: final diff and test output.

- [ ] **Step 1: Run `git diff --check` and inspect the final diff.**
- [ ] **Step 2: Request an independent code review of the completed change.**
- [ ] **Step 3: Fix critical or important findings and rerun affected tests.**
- [ ] **Step 4: Report changed files, verification results, and remaining environment-dependent checks.**

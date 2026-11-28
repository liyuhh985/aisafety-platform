> 状态：implemented
> 最后核对：2026-10-09
> 历史文档：当前版本请以 docs/current/ 和代码为准。

# Frontend Report Closeout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the cloud Vue report workflow from history navigation through authenticated detail viewing without changing unrelated business behavior.

**Architecture:** Keep the existing API wrapper, authentication storage, and page styling. Add the missing `/report/:id` route and a focused detail view that requests the flat report DTO with the current Bearer token, distinguishes loading, empty, and error states, and provides navigation back to history or analysis.

**Tech Stack:** Vue 3, Vue Router, existing project HTTP helpers, Vite, Nginx static deployment.

## Global Constraints

- Modify only the cloud frontend files needed for the report closeout.
- Preserve existing uncommitted changes in `AnalysisView.vue`, `HistoryView.vue`, and `MapPage.vue`.
- Use `Authorization: Bearer <token>` for report requests.
- Support flat fields `hazardCategory`, `severity`, `description`, `rectification`, `reportText`, and `createTime`.
- Do not expose real API keys, tokens, passwords, `.env` files, or unrelated deployment configuration.
- Run `npm run build` only after a source change, and preserve the existing deployment assets.

### Task 1: Inspect the remote frontend and deployed entry

**Files:**
- Read: `/home/ubuntu/aisafety-platform-frontend/src/views/AnalysisView.vue`
- Read: `/home/ubuntu/aisafety-platform-frontend/src/views/HistoryView.vue`
- Read: `/home/ubuntu/aisafety-platform-frontend/src/router/index.js`
- Read: `/var/www/safety-platform/index.html`

- [ ] **Step 1: Record the remote branch and dirty files**

Run `git -C /home/ubuntu/aisafety-platform-frontend status --short --branch` on the cloud host and preserve all existing source edits.

- [ ] **Step 2: Confirm the current request contract**

Verify the history and analysis code use `/api/report`, `/api/report/{id}`, and `Authorization: Bearer ${token}` while mapping flat backend fields before making a change.

### Task 2: Add the missing report detail workflow

**Files:**
- Create: `/home/ubuntu/aisafety-platform-frontend/src/views/ReportDetailView.vue`
- Modify: `/home/ubuntu/aisafety-platform-frontend/src/router/index.js`
- Modify: `/home/ubuntu/aisafety-platform-frontend/src/views/HistoryView.vue` only if its existing field mapping prevents navigation or display

**Interfaces:**
- Consumes: route param `id`, current login token, `GET /api/report/{id}` response.
- Produces: a registered `/report/:id` view with report text, rectification suggestions, flat-field metadata, explicit API errors, and navigation actions.

- [ ] **Step 1: Implement the detail view states**

Load the route id on mount, send the Bearer token, normalize `rectification` from an array or JSON string, and render separate loading, not-found/permission, network-error, and populated states. Never render an API failure as an empty report.

- [ ] **Step 2: Register the route using the existing router style**

Add `/report/:id` with the project’s existing auth guard/layout conventions and retain the current history and analysis routes.

- [ ] **Step 3: Run a static contract check**

Search the changed source for the route, endpoint, Bearer header, and required fields. Confirm no secret or environment file was added.

### Task 3: Build and verify the deployed entry

**Files:**
- Modify: `/var/www/safety-platform` only through the project’s existing deployment command after build succeeds

- [ ] **Step 1: Build the Vue application**

Run `npm run build` in `/home/ubuntu/aisafety-platform-frontend`; stop and report the first build error if it fails.

- [ ] **Step 2: Preserve old assets and deploy the new build**

Use the existing deployment procedure without deleting old assets, then inspect `/var/www/safety-platform/index.html` to identify the actual new entry bundle.

- [ ] **Step 3: Verify the production bundle statically**

Confirm the new bundle contains the `/report/` route, `/api/report/` detail request, Bearer authentication, report text, and rectification rendering.

- [ ] **Step 4: Report runtime gaps honestly**

Without fabricating credentials, report which HTTP statuses were observed for upload, save, list, detail, and delete, and identify any browser-only checks that remain unverified.

# Test Suite & LLM Toggle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task.

**Goal:** Replace the stress test with a professional test suite that seeds a realistic test database and evaluates it with a dummy/real LLM toggle.

**Architecture:** Remove all HTTP-load stress testing. Replace with direct-DB seeding of realistic prompts (500 words x 5 categories x N participants). Add an admin-panel LLM mode toggle (dummy vs. real Gemini) threaded through the evaluation pipeline as a request parameter.

**Tech Stack:** Python/FastAPI backend, React/TypeScript frontend, Supabase PostgreSQL, Gemini 2.5 Flash, google-generativeai SDK.

---

## Capacity Assessment

**Can the website handle 300 users x 5 prompts = 1,500 submissions?**

| Component | Load | Verdict |
|---|---|---|
| FastAPI (Render free) | 1,500 lightweight POST requests, spread over hours/days | Trivial |
| Supabase (free tier) | 1,500 text inserts (~5 per submission) | Trivial |
| Evaluation (dummy LLM) | 1,500 in-process evals, ~0ms each | Instant |
| Evaluation (Gemini) | 150 batched calls (10 prompts/call), ~5s each | ~12 min |

**Bottleneck is evaluation, not submission.** Submissions are just text saves.

---

## File Structure

### Files to Create
| File | Responsibility |
|---|---|
| `backend/app/services/test_seeding_service.py` | Generate realistic 500-word prompts, seed participants + submissions + responses directly into DB |
| `backend/tests/test_seeding_service.py` | Tests for seeding: correct counts, prompt lengths, category coverage |

### Files to Modify
| File | Changes |
|---|---|
| `backend/app/api/admin.py` | Remove stress endpoints. Add /test/seed, /test/llm-mode, /test/eval. |
| `backend/app/services/eval_run_service.py` | Accept llm_mode param. Remove run_pipeline(). |
| `backend/app/services/evaluation_service.py` | process_batch_group() accepts llm_mode. |
| `backend/app/services/submission_service.py` | run_batch_evaluator() accepts llm_mode. |
| `backend/app/config.py` | Remove stress_* settings. |
| `frontend/src/pages/admin.tsx` | Replace StressPanel with TestSuitePanel. Update tabs. |
| `frontend/src/services/api.ts` | Replace stress API methods with test suite methods. |
| `frontend/src/types/index.ts` | Replace StressStatus with TestSuiteStatus. |

### Files to Delete
| File | Reason |
|---|---|
| `backend/app/services/stress_test_service.py` | HTTP-load stress test replaced by DB seeding |
| `backend/app/services/stress_cleanup_service.py` | Cleanup now in test_seeding_service |
| `scripts/stress_test.py` | CLI stress test removed |
| `backend/tests/test_stress_runner.py` | Tests for removed stress test |

---

## Task 1: Remove Stress Test Backend

**Files:**
- Modify: `backend/app/api/admin.py`
- Modify: `backend/app/config.py`
- Modify: `backend/app/services/eval_run_service.py`
- Delete: `stress_test_service.py`, `stress_cleanup_service.py`, `scripts/stress_test.py`, `tests/test_stress_runner.py`

- [ ] Remove stress imports and endpoints from admin.py
- [ ] Remove stress settings from config.py
- [ ] Delete stress-only files
- [ ] Remove run_pipeline() from eval_run_service.py
- [ ] Run tests
- [ ] Commit: "refactor: remove stress test system (HTTP-load based)"

---

## Task 2: Create Test Seeding Service

**Files:**
- Create: `backend/app/services/test_seeding_service.py`
- Create: `backend/tests/test_seeding_service.py`

- [ ] Write test file (TDD) with tests for prompt generation and seeding
- [ ] Run tests to verify they fail (module not found)
- [ ] Implement test_seeding_service.py with:
  - CATEGORIES list (5 categories)
  - CATEGORY_TEMPLATES dict (2 templates per category with fill-in variables)
  - FILL_INS dict (word lists for template variables)
  - generate_prompts_for_category() (~500 words per prompt)
  - seed_test_data(participant_count) (direct DB inserts)
  - cleanup_test_data()
- [ ] Run tests to verify they pass
- [ ] Run full test suite
- [ ] Commit: "feat: add test seeding service with realistic prompt generation"

---

## Task 3: Add LLM Mode Toggle to Evaluation Pipeline

**Files:**
- Modify: `backend/app/services/submission_service.py`
- Modify: `backend/app/services/evaluation_service.py`
- Modify: `backend/app/services/eval_run_service.py`
- Modify: `backend/app/api/admin.py`

- [ ] Add llm_mode param to run_batch_evaluator()
- [ ] Thread llm_mode through evaluation_service
- [ ] Thread llm_mode through eval_run_service
- [ ] Add /test/llm-mode GET+POST endpoints
- [ ] Add llm_mode to EvalStartRequest
- [ ] Run tests
- [ ] Commit: "feat: add llm_mode parameter threading through evaluation pipeline"

---

## Task 4: Add Test Suite API Endpoints

**Files:**
- Modify: `backend/app/api/admin.py`

- [ ] Add POST /test/seed (seed test data)
- [ ] Add POST /test/cleanup (clean test data)
- [ ] Add GET /test/status (test competition stats)
- [ ] Run tests and commit: "feat: add test suite API endpoints"

---

## Task 5: Replace StressPanel with TestSuitePanel in Frontend

**Files:**
- Modify: `frontend/src/pages/admin.tsx`
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/types/index.ts`

- [ ] Update TypeScript types (TestSuiteStatus, LlmModeResponse, SeedResult, CleanupResult)
- [ ] Update API methods (replace stress methods with test suite methods)
- [ ] Create TestSuitePanel component with:
  - DB Seeding section (participant count, Seed button, Cleanup, live stats)
  - LLM Mode section (Dummy/Gemini toggle)
  - Evaluation trigger (Run Evaluation button)
- [ ] Update tab navigation (stress -> test)
- [ ] Remove stress button from Dashboard
- [ ] Remove stress cleanup from Export panel
- [ ] Build and verify (npm run build)
- [ ] Commit: "feat: replace stress test with test suite panel in admin UI"

---

## Task 6: Clean Up Scripts and Docs

- [ ] Update e2e test to use test_seeding_service
- [ ] Update README and SETUP docs
- [ ] Final test run (backend + frontend)
- [ ] Commit: "docs: update documentation for test suite workflow"

---

## Final Verification

- [ ] All backend tests pass (31+ tests)
- [ ] Frontend builds clean (tsc + vite)
- [ ] No references to stress_test remain in codebase
- [ ] Test seeding generates realistic ~500-word prompts
- [ ] LLM mode toggle works (dummy = instant, gemini = real API)
- [ ] Admin panel shows Test Suite tab with seed/eval/cleanup

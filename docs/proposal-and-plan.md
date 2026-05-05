# RHEL Modernize Agent: Proposal and Implementation Plan

**Authors:** Twinkll Sisodia
**Date:** May 5, 2026
**Status:** Proposal / Draft
**Tracking Issue:** [ai-quickstart-contrib #44](https://github.com/rh-ai-quickstart/ai-quickstart-contrib/issues/44)

---

## 1. Executive Summary

We are building an AI-powered quickstart that automates the migration of legacy applications running on RHEL 7/8/9 to RHEL 10. The solution uses an **agent mesh** -- a coordinated set of specialized AI agents -- running entirely on Red Hat OpenShift AI with no dependency on external cloud APIs.

This addresses a recurring demand from defense and aerospace customers (L3Harris, Boeing, and others) who face the challenge of modernizing thousands of legacy applications. Manual migration at this scale requires thousands of engineer-hours and is not feasible. The agent mesh approach reduces this to a fraction of the effort while maintaining full auditability and human oversight.

**The ask:** Build a repeatable, productizable quickstart that a customer or field team can deploy on OpenShift AI, point at a legacy Git repository, and get back analyzed code, a migration plan, and refactored code as pull requests -- all without internet connectivity.

---

## 2. Background and Motivation

### 2.1 Why This Matters

Legacy software estates on older RHEL versions are a growing liability:

- **Security:** Unpatched codebases, deprecated cryptographic libraries (OpenSSL 1.x), missing hardening
- **Compliance:** GSA AI governance framework and DoD directives mandate traceable, auditable modernization
- **Operational cost:** Maintaining legacy systems consumes engineering capacity that could be building new capabilities
- **Scale problem:** A single defense contractor may have hundreds of applications across RHEL 7, 8, and 9 that all need to reach RHEL 10

### 2.2 Why Now

- RHEL 10 is the target platform with modern security hardening and runtime support
- The defense and aerospace sector is actively requesting Red Hat's help with this problem
- L3Harris engagement demonstrated the approach works but needs to be productized
- OpenShift AI now has the infrastructure (vLLM, GPU operator, disconnected support) to run this entirely on-premise

### 2.3 Prior Art

The team (Dan Domkowski, Omotola Awofolu) has already built and validated this approach in a customer engagement. The current implementation uses:

- Jupyter notebook-driven workflows on RHOAI
- 3 custom workbench images (synthetic data gen, code understanding, code migration)
- GraphRAG (Microsoft) for code indexing with LanceDB
- InstructLab SDK for synthetic data generation
- CrewAI for agent orchestration
- Models served via vLLM (gpt-oss-120B, Devstral, Ministral, e5-mistral)

**The goal of this quickstart is to package this into a repeatable, self-contained experience.**

---

## 3. What We're Building

### 3.1 Inputs

| Input | Description |
|-------|-------------|
| Git repository URL(s) | One or more repositories containing the legacy application source code |
| Branch name | The branch to analyze and migrate |
| Target RHEL version | RHEL 10 (default), configurable |
| Migration type | Python 2→3, Java version upgrade, C++ toolchain, or general RHEL compatibility |

### 3.2 Outputs

| Output | Description |
|--------|-------------|
| Code knowledge graph | Queryable GraphRAG index of the entire codebase |
| Canned analysis report | Pre-answered migration questions: deprecated APIs, dependency risks, complexity estimate |
| Refactoring catalog | Every required change identified, categorized, and prioritized |
| Migration plan | Structured user stories with dependency ordering |
| Kanban board | Git issues created and organized for tracking |
| Refactored code | Pull requests with migrated code + test suites |
| Functional equivalence tests | Test suites verifying identical behavior post-migration |

### 3.3 User Experience

A user should be able to:

1. Deploy the quickstart on their OpenShift AI cluster (one-time setup)
2. Open a Jupyter notebook
3. Enter their Git repo URL
4. Run notebooks sequentially through the 3 phases
5. Review generated PRs and merge

No frontier model access, no internet connection, no external dependencies at runtime.

---

## 4. Detailed Phase Plan

### Phase 1: Code Archaeology and Understanding

**Duration:** Days 1-30
**Goal:** Build a deep, queryable understanding of the legacy codebase before making any changes.

#### 4.1.1 Synthetic Data Generation

| Item | Detail |
|------|--------|
| **What** | Pre-process source code into structured format with metadata |
| **Tool** | InstructLab Gen 2 SDK (decomposed module approach) |
| **Input** | Git repo URL + branch |
| **Output** | Structured code representation with metadata annotations |
| **Language support** | Language-agnostic -- handles Python, Java, C++, and others |
| **Workbench image** | `workbench-synth-datagen` |

#### 4.1.2 GraphRAG Code Indexing

| Item | Detail |
|------|--------|
| **What** | Build a hierarchical knowledge graph of the codebase |
| **Tool** | Microsoft GraphRAG framework + LanceDB |
| **Processing time** | ~1 hour for a typical repository |
| **Summarization method** | Leiden algorithm, bottom-up hierarchical summarization |
| **Model** | gpt-oss-120B for graph construction, e5-mistral-7B for embeddings |
| **Workbench image** | `workbench-code-understanding` |

**Why GraphRAG over standard RAG or long-context LLMs?**

| Approach | Limitation |
|----------|-----------|
| Long-context LLM (e.g., Claude, GPT) | Degrades as context window fills. Compaction loses details. Trained on public code, not your proprietary legacy code. Bound to single repo. |
| Standard RAG | Chunk-based retrieval misses cross-file relationships and architectural patterns |
| **GraphRAG** | Hierarchical summarization preserves details. Multi-repo indexing. Bottom-up approach doesn't leave information behind. Works with code never seen in training. |

#### 4.1.3 Analysis and Reporting

Once the index is built, the system produces:

**Automated reports (canned questions):**
- What deprecated APIs are used and what are their modern equivalents?
- What are the dependency risks for RHEL 10?
- What is the estimated migration complexity per module?
- What is the recommended migration sequence?
- What are the most tightly coupled components?

**Interactive querying (GUI):**
- Ad-hoc questions about the codebase
- "What does this module do?"
- "What depends on libfoo?"
- "What's the risk of upgrading this dependency?"

**Deliverables:**
- Refactoring catalog (JSON/markdown)
- Dependency map with RHEL 10 compatibility status
- Recommended migration path (ordered list of changes)
- Risk assessment per module

#### 4.1.4 Tasks to Build Phase 1

| # | Task | Description | Dependencies | Est. Effort |
|---|------|-------------|-------------|-------------|
| 1.1 | Dockerfile: synth-datagen image | Build workbench image with InstructLab SDK deps | None | 2-3 days |
| 1.2 | Dockerfile: code-understanding image | Build workbench image with GraphRAG, LanceDB, embedding deps | None | 2-3 days |
| 1.3 | Notebook: synthetic data generation | Jupyter notebook that takes repo URL, clones, pre-processes | 1.1 | 3-5 days |
| 1.4 | Notebook: GraphRAG indexing | Jupyter notebook that builds the knowledge graph | 1.2, 1.3 | 5-7 days |
| 1.5 | Notebook: canned report generation | Jupyter notebook that runs pre-defined queries and generates markdown report | 1.4 | 3-5 days |
| 1.6 | Interactive query GUI | Simple UI for ad-hoc code questions (can be Gradio or JupyterLab extension) | 1.4 | 3-5 days |
| 1.7 | vLLM model serving setup | Deploy gpt-oss-120B and e5-mistral-7B on OpenShift AI | None | 2-3 days |
| 1.8 | End-to-end test: Phase 1 | Run full pipeline on a sample legacy repo | 1.3-1.7 | 3-5 days |

**Phase 1 total estimate: 3-5 weeks**

---

### Phase 2: Migration Planning

**Duration:** Days 30-60
**Goal:** Convert Phase 1 analysis into an actionable, trackable migration plan.

#### 4.2.1 Plan Generation

| Item | Detail |
|------|--------|
| **Input** | Refactoring catalog + dependency map from Phase 1 |
| **Output** | Structured migration plan as user stories |
| **Model** | Ministral-3-14B for reasoning and structured output |
| **Framework** | CrewAI for agent orchestration |

The planning agent:
1. Takes the refactoring catalog and groups related changes into logical units of work
2. Determines dependency ordering (e.g., "update library X before refactoring module Y")
3. Estimates complexity per story (S/M/L)
4. Generates acceptance criteria for each story
5. Creates Git issues and organizes them on a Kanban board

#### 4.2.2 Story Structure

Each generated user story follows this format:

```
Title: [Migration Type] - [Component] - [Specific Change]

Description:
- What needs to change and why
- Current state (deprecated API / old pattern)
- Target state (modern equivalent)
- Files affected
- Dependencies on other stories

Acceptance Criteria:
- [ ] Code compiles with RHEL 10 toolchain
- [ ] Functional equivalence tests pass
- [ ] No regression in dependent modules
- [ ] Code review approved

Complexity: S / M / L
Priority: P1 / P2 / P3 (based on dependency ordering)
```

#### 4.2.3 Kanban Board

Stories are automatically created as Git issues and organized into columns:

| Column | Description |
|--------|-------------|
| **Backlog** | All stories, prioritized by dependency order |
| **In Progress** | Story currently being processed by coding agent |
| **Review** | PR generated, awaiting human review |
| **Blocked** | Automated checks failed, needs human input |
| **Done** | PR merged, story complete |

#### 4.2.4 Tasks to Build Phase 2

| # | Task | Description | Dependencies | Est. Effort |
|---|------|-------------|-------------|-------------|
| 2.1 | Planning agent (CrewAI) | Agent that converts refactoring catalog to stories | Phase 1 complete | 5-7 days |
| 2.2 | Story generation templates | Prompt templates for structured story output | 2.1 | 2-3 days |
| 2.3 | Git issue creation | Integration with GitHub/GitLab API for issue creation | 2.1 | 2-3 days |
| 2.4 | Kanban board setup | Automated board creation and story organization | 2.3 | 2-3 days |
| 2.5 | Dependency ordering algorithm | Topological sort of stories based on code dependencies | 2.1 | 3-5 days |
| 2.6 | Notebook: migration planning | Jupyter notebook that orchestrates Phase 2 | 2.1-2.5 | 3-5 days |
| 2.7 | Human review checkpoint | UI/notebook step for reviewing and approving the plan | 2.6 | 2-3 days |
| 2.8 | End-to-end test: Phase 2 | Run planning on Phase 1 output from sample repo | 2.6 | 2-3 days |

**Phase 2 total estimate: 3-4 weeks**

---

### Phase 3: Agentic Code Transformation

**Duration:** Days 60-90
**Goal:** Execute the migration plan through coordinated AI agents, producing reviewed pull requests.

#### 4.3.1 Agent Mesh Architecture

Four harnesses coordinate the transformation:

```
┌─────────────────────────────────────────────────────────────┐
│                        PM Harness                           │
│              (Orchestrates the full workflow)                │
│                                                             │
│  ┌──────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │ Backlog  │───>│ In Progress  │───>│   Review     │       │
│  │          │    │              │    │              │       │
│  │          │<───│   Blocked    │<───│              │       │
│  └──────────┘    └──────┬───────┘    └──────────────┘       │
│                         │                                    │
└─────────────────────────┼────────────────────────────────────┘
                          │
            ┌─────────────┼─────────────┐
            │             │             │
            v             v             v
   ┌────────────┐ ┌──────────────┐ ┌──────────┐
   │   Coding   │ │  Evaluation  │ │    CI    │
   │  Harness   │ │   Harness    │ │  Harness │
   │            │ │              │ │          │
   │ - Analyze  │ │ - Generate   │ │ - Gather │
   │ - Refactor │ │   test suite │ │   artifacts│
   │ - Generate │ │ - Verify     │ │ - Create │
   │   code     │ │   equivalence│ │   PR     │
   └────────────┘ └──────────────┘ └──────────┘
```

#### 4.3.2 Harness Details

**PM Harness (Orchestrator)**
- Framework: CrewAI
- Model: Mistral / Ministral-3-14B
- Responsibilities:
  - Pick next story from backlog based on priority
  - Dispatch to coding harness
  - Monitor progress
  - Move stories between Kanban columns
  - Handle blocked items (escalate to human)

**Coding Harness**
- Model: gpt-oss-120B / Devstral-Small-24B
- Responsibilities:
  - Analyze the story's target files using the GraphRAG index
  - Generate refactored code using OpenCode and OpenSpec patterns
  - Ensure the refactored code compiles with RHEL 10 toolchain
  - Handle multi-file changes that span a single story

**Evaluation Harness**
- Framework: CrewAI
- Model: Mistral
- Responsibilities:
  - Generate characterization tests capturing original behavior
  - Create functional equivalence test suite
  - Run tests against both original and refactored code
  - Report pass/fail with detailed diff on failures
  - Target: 80% test coverage on migrated code

**CI Harness**
- Framework: CrewAI
- Model: Mistral
- Responsibilities:
  - Collect all artifacts (code changes, tests, analysis)
  - Create a pull request with structured description
  - Include checklist of verification items
  - If all checks pass: PR ready for review
  - If checks fail: move story to Blocked column with failure details

#### 4.3.3 Human-in-the-Loop Workflow

```
Story picked from backlog
        │
        v
  Coding agent generates code
        │
        v
  Evaluation agent generates tests
        │
        ├── Tests pass ──> CI creates PR ──> Human reviews ──> Merge
        │
        └── Tests fail ──> Story moves to Blocked
                                │
                                v
                    Human reviews failure
                                │
                                v
                    Human adds guidance, moves to Backlog
                                │
                                v
                          Retry cycle
```

#### 4.3.4 Tasks to Build Phase 3

| # | Task | Description | Dependencies | Est. Effort |
|---|------|-------------|-------------|-------------|
| 3.1 | Dockerfile: code-migration image | Build workbench image with CrewAI, vLLM client, OpenCode/OpenSpec | None | 3-5 days |
| 3.2 | PM harness agent | CrewAI agent for orchestration and story management | 3.1, Phase 2 | 5-7 days |
| 3.3 | Coding harness agent | Agent for code analysis and refactoring | 3.1 | 7-10 days |
| 3.4 | Evaluation harness agent | Agent for test generation and equivalence verification | 3.1 | 5-7 days |
| 3.5 | CI harness agent | Agent for artifact collection and PR creation | 3.1 | 3-5 days |
| 3.6 | Agent mesh integration | Wire all harnesses together, message passing, state management | 3.2-3.5 | 5-7 days |
| 3.7 | Blocked story handler | Workflow for human escalation and re-queuing | 3.6 | 2-3 days |
| 3.8 | Notebook: code migration | Jupyter notebook that orchestrates Phase 3 | 3.6 | 3-5 days |
| 3.9 | vLLM model serving: coding models | Deploy Devstral-24B and Ministral-14B | None | 2-3 days |
| 3.10 | End-to-end test: Phase 3 | Run full transformation on sample repo | 3.8 | 5-7 days |
| 3.11 | End-to-end test: Full pipeline | Run Phase 1 → 2 → 3 on a real legacy repo | 3.10 | 5-7 days |

**Phase 3 total estimate: 6-8 weeks**

---

## 5. Infrastructure and Deployment

### 5.1 Model Serving

All models are served via vLLM on OpenShift AI:

| Model | Parameters | GPU Requirement | Serving Config |
|-------|-----------|----------------|---------------|
| gpt-oss-120B | 120B | Multi-GPU (2x L40S or equivalent) | vLLM, tensor parallelism |
| Devstral-Small-24B | 24B | Single GPU (1x L40S) | vLLM |
| Ministral-3-14B | 14B | Single GPU (1x L40S or smaller) | vLLM |
| e5-mistral-7B | 7B | Single GPU (1x T4 or equivalent) | vLLM |

### 5.2 Disconnected / Air-Gapped Deployment

The system must work without internet access:

- All model weights pre-downloaded and stored in cluster storage
- All Python/Java dependencies bundled in workbench images
- No external API calls at runtime
- Git operations work against internal Git server (GitLab/Gitea)
- Container images available from internal registry

### 5.3 Deployment Artifacts

| Artifact | Description |
|----------|-------------|
| 3x Dockerfiles | Workbench images for synth-datagen, code-understanding, code-migration |
| Helm chart or install script | One-command deployment of all components |
| Model weight bundles | Pre-packaged model weights for air-gapped transfer |
| Sample legacy repo | Test repository for validating the pipeline |

---

## 6. Timeline and Milestones

| Milestone | Target Date | Deliverable |
|-----------|------------|-------------|
| **M0: Proposal approved** | Week 1 | This document reviewed and signed off |
| **M1: Infrastructure ready** | Week 2-3 | vLLM serving all 4 models, workbench images built |
| **M2: Phase 1 complete** | Week 6-8 | Code archaeology pipeline working end-to-end |
| **M3: Phase 2 complete** | Week 10-12 | Migration planning pipeline working end-to-end |
| **M4: Phase 3 complete** | Week 16-18 | Agent mesh transformation pipeline working end-to-end |
| **M5: Full pipeline validated** | Week 19-20 | End-to-end test on a real legacy repo |
| **M6: Quickstart packaged** | Week 21-22 | Installable quickstart with documentation |

**Total estimated duration: ~22 weeks (5-6 months)**

---

## 7. Risks and Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|-----------|------------|
| gpt-oss-120B requires more GPU than available | Can't run coding agent | Medium | Fall back to Devstral-24B for all coding tasks; test with both |
| GraphRAG indexing too slow for very large repos | Phase 1 becomes multi-day | Medium | Implement incremental indexing; parallelize across modules |
| Generated code has subtle behavioral differences | Functional equivalence failures | High | Characterization tests before refactoring; human review of all PRs |
| CrewAI agent loops or excessive reasoning | Hung pipeline, wasted compute | Medium | Set hard timeouts per story; circuit breaker pattern |
| Disconnected environment has no Git server | Can't create issues or PRs | Low | Support local-only mode with file-based tracking |
| Model weights too large for air-gapped transfer | Deployment blocked | Low | Quantized model variants; prioritize smaller models |

---

## 8. Open Questions

| # | Question | Owner | Status |
|---|----------|-------|--------|
| 1 | What sample legacy repo should we use for testing? | Team | Open |
| 2 | Should we support GitLab, GitHub, or both for issue tracking? | Dan | Open |
| 3 | What is the minimum GPU configuration we should support? | Omotola | Open |
| 4 | Should Phase 1 reports be markdown, HTML, or PDF? | Twinkll | Open |
| 5 | Do we need to support partial migrations (e.g., only Python, skip Java)? | Team | Open |
| 6 | How do we handle repos with no existing tests? | Dan | Open |
| 7 | Should the quickstart include fine-tuning on customer code, or is base model sufficient? | Omotola | Open |
| 8 | What is the handoff plan from existing notebook workflow to packaged quickstart? | Team | Open |

---

## 9. Success Criteria

The quickstart is considered successful when:

1. **Deployable in < 1 day** on a properly configured OpenShift AI cluster
2. **Runs fully disconnected** with no external API calls
3. **End-to-end demo** works on a sample legacy repo: repo in → PRs out
4. **80% test coverage** on migrated code with functional equivalence validation
5. **Repeatable** -- different users, different repos, consistent results
6. **Documented** -- README, notebooks, and architecture docs sufficient for self-service

---

## 10. Team and Responsibilities

| Person | Role | Focus Area |
|--------|------|------------|
| **Dan Domkowski** | Technical lead | Agent mesh architecture, coding harness, prior engagement experience |
| **Omotola Awofolu** | Technical lead | Workbench images, GraphRAG pipeline, model serving |
| **Twinkll Sisodia** | Quickstart lead | Packaging, documentation, integration, quickstart catalog |

---

## Appendix A: Glossary

| Term | Definition |
|------|-----------|
| **Agent mesh** | A coordinated set of specialized AI agents, each handling a specific task in the migration pipeline |
| **GraphRAG** | Graph-based Retrieval Augmented Generation -- builds a knowledge graph from source code for deep querying |
| **Harness** | A wrapper around an AI agent that manages its inputs, outputs, and lifecycle |
| **Characterization test** | A test that captures the existing behavior of code before refactoring, to verify nothing changes |
| **Functional equivalence** | The property that migrated code produces identical outputs to the original given identical inputs |
| **OpenCode / OpenSpec** | Patterns for structured code generation and specification |
| **Leiden algorithm** | Community detection algorithm used for hierarchical summarization in GraphRAG |
| **LanceDB** | Embedded vector database used to store and query the GraphRAG index |
| **vLLM** | High-performance inference engine for serving LLMs |
| **CrewAI** | Framework for orchestrating multiple AI agents |

## Appendix B: Reference Links

- [Red Hat Blog: Agent Mesh Approach to Legacy System Modernization](https://www.redhat.com/en/blog/refactoring-speed-mission-agent-mesh-approach-legacy-system-modernization-red-hat-ai)
- [GitHub Issue: RHEL 10 Modernization Agent Quickstart](https://github.com/rh-ai-quickstart/ai-quickstart-contrib/issues/44)
- [Microsoft GraphRAG](https://github.com/microsoft/graphrag)
- [InstructLab](https://github.com/instructlab)
- [CrewAI](https://github.com/crewAIInc/crewAI)
- [vLLM](https://github.com/vllm-project/vllm)
- [LanceDB](https://github.com/lancedb/lancedb)
- [Red Hat OpenShift AI](https://www.redhat.com/en/technologies/cloud-computing/openshift/openshift-ai)

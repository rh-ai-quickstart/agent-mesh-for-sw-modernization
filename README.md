# RHEL Modernize Agent: AI-Driven Legacy System Migration

Accelerate legacy application modernization to RHEL 10 using an agent mesh of specialized AI agents running entirely on Red Hat AI -- no cloud APIs required.

## Table of contents

- [Overview](#overview)
- [The Problem](#the-problem)
- [How It Works](#how-it-works)
  - [Phase 1: Code Archaeology (Days 1-30)](#phase-1-code-archaeology-days-1-30)
  - [Phase 2: Migration Planning (Days 30-60)](#phase-2-migration-planning-days-30-60)
  - [Phase 3: Agentic Code Transformation (Days 60-90)](#phase-3-agentic-code-transformation-days-60-90)
- [Architecture](#architecture)
  - [Agent Mesh Design](#agent-mesh-design)
  - [Workbench Images](#workbench-images)
  - [Model Stack](#model-stack)
- [User Journey](#user-journey)
  - [Getting Started](#getting-started)
  - [Step 1: Point to Your Legacy Repo](#step-1-point-to-your-legacy-repo)
  - [Step 2: Understand Your Codebase](#step-2-understand-your-codebase)
  - [Step 3: Generate a Migration Plan](#step-3-generate-a-migration-plan)
  - [Step 4: Execute the Migration](#step-4-execute-the-migration)
  - [Step 5: Review and Merge](#step-5-review-and-merge)
- [Requirements](#requirements)
  - [Minimum Hardware Requirements](#minimum-hardware-requirements)
  - [Minimum Software Requirements](#minimum-software-requirements)
- [What Gets Migrated](#what-gets-migrated)
- [Key Design Decisions](#key-design-decisions)
- [Success Metrics](#success-metrics)
- [References](#references)
- [Tags](#tags)

## Overview

Organizations running mission-critical applications on RHEL 7/8/9 face a growing modernization challenge. Migrating thousands of legacy applications to RHEL 10 manually requires enormous human effort -- L3Harris estimated thousands of engineer-hours for their migration alone.

This quickstart deploys an **agent mesh** -- a coordinated set of specialized AI agents -- that automates the heavy lifting of legacy code analysis, migration planning, and code refactoring. It runs entirely within your infrastructure on Red Hat OpenShift AI, making it suitable for disconnected and air-gapped environments common in defense and regulated industries.

**What you give it:** A Git repository URL containing your legacy application code.

**What you get back:** A fully analyzed codebase with a migration plan, refactored code, test suites, and pull requests ready for human review.

## The Problem

Legacy software estates running on older RHEL versions create compounding operational risk:

- **Security exposure:** Aging codebases miss critical patches and lack modern security hardening
- **Technical debt:** Deprecated APIs, outdated language runtimes (Python 2, older Java/GCC), and missing test coverage
- **Scale:** Manual migration at enterprise scale (hundreds to thousands of applications) is not feasible with existing teams
- **Compliance:** Government and defense mandates (GSA AI governance, DoD directives) require auditable, traceable modernization
- **Disconnected operations:** Defense and aerospace environments (ships, remote facilities) cannot depend on cloud-hosted AI services

## How It Works

The migration proceeds through three phases, each driven by Jupyter notebook workflows running on Red Hat OpenShift AI.

### Phase 1: Code Archaeology (Days 1-30)

**Goal:** Deeply understand the legacy codebase before changing anything.

A GraphRAG-based knowledge graph is built from your source code using hierarchical bottom-up summarization. Unlike standard LLM approaches that degrade as context windows fill up, this approach indexes the entire codebase into a queryable graph backed by LanceDB -- no details get left behind, even for large legacy codebases that have never been publicly shared.

**What happens:**
1. The synthetic data generation workbench pre-processes your code into structured format with metadata (language-agnostic)
2. The code understanding workbench builds a GraphRAG index (~1 hour for typical repos)
3. Automated analysis produces:
   - **Refactoring catalog** -- every deprecated API, outdated pattern, and compatibility issue identified
   - **Dependency map** -- full dependency graph with RHEL 10 compatibility status
   - **Recommended migration path** -- prioritized sequence of changes
   - **Canned reports** with answers to pre-defined migration questions

**You can also:** Query the index interactively through a GUI to ask ad-hoc questions about your codebase -- useful for archaeology on codebases with little or no documentation.

### Phase 2: Migration Planning (Days 30-60)

**Goal:** Create a concrete, actionable migration plan from Phase 1 analysis.

Using the refactoring catalog and dependency map from Phase 1, the system generates:

- A structured migration plan broken into user stories
- Each story mapped to specific code changes required
- Stories organized into a Kanban board via Git issues
- Prioritization based on dependency order and risk

### Phase 3: Agentic Code Transformation (Days 60-90)

**Goal:** Execute the migration plan through coordinated AI agents.

A **PM harness** orchestrates the work:

1. **Plan creation** -- Converts the migration plan into executable user stories
2. **Story processing** -- A coding harness picks up stories from the backlog:
   - **Code generation** using OpenCode and OpenSpec patterns
   - **Evaluation harness** converts each change into a test suite for functional equivalence
   - **CI harness** gathers artifacts and creates pull requests
3. **Human-in-the-loop** -- If automated checks fail, stories move to a "blocked" column for human review, then back to the backlog
4. **Target:** 80% test coverage with functional equivalence validation

## Architecture

### Agent Mesh Design

Rather than a single monolithic agent, the system uses a mesh of specialized agents, each optimized for a specific task:

```
                    +------------------+
                    |   PM Harness     |
                    | (Orchestration)  |
                    +--------+---------+
                             |
              +--------------+--------------+
              |              |              |
     +--------v---+  +-------v----+  +------v-------+
     |   Coding   |  | Evaluation |  |     CI       |
     |   Harness  |  |  Harness   |  |   Harness    |
     +--------+---+  +-------+----+  +------+-------+
              |              |              |
              v              v              v
         Code changes   Test suites    Pull requests
```

| Harness | Role | Framework | Model |
|---------|------|-----------|-------|
| **PM Harness** | Orchestration, story management, Kanban board | CrewAI | Mistral / Ministral |
| **Coding Harness** | Code analysis, refactoring, generation | OpenCode / OpenSpec | gpt-oss-120B / Devstral-Small-24B |
| **Evaluation Harness** | Test generation, functional equivalence | CrewAI | Mistral |
| **CI Harness** | Artifact collection, PR creation | CrewAI | Mistral |
| **Tracking Agent** | GitLab/GitHub issue management | Custom | Ministral-3-14B |

### Workbench Images

Three custom RHOAI workbench images (Dockerfiles provided to build from scratch):

| Image | Purpose | Key Dependencies |
|-------|---------|-----------------|
| **Synthetic Data Generation** | Pre-processes code repos into structured training format using InstructLab Gen 2 SDK | InstructLab SDK modules |
| **Code Understanding** | Builds and queries GraphRAG index for deep code analysis | GraphRAG (Microsoft), LanceDB, embedding libraries |
| **Code Migration** | Executes the agentic migration workflow | CrewAI, vLLM client, OpenCode/OpenSpec |

### Model Stack

All models run locally via vLLM on OpenShift AI -- no external API calls required:

| Model | Parameters | Purpose | Context Window |
|-------|-----------|---------|----------------|
| **gpt-oss-120B** | 120B | Primary coding agent, GraphRAG construction | 128K |
| **Devstral-Small-24B** | 24B | Code analysis, refactoring | 256K |
| **Ministral-3-14B** | 14B | Reasoning, orchestration, structured analysis | - |
| **e5-mistral-7B** | 7B | Embedding and vector retrieval | - |

**Why smaller models?** Small language models are well suited for agentic workflows requiring reliable, repeatable execution and low-latency responses. They produce sharper probability distributions and more consistent outputs than frontier models, while fitting within the compute constraints of disconnected environments.

## User Journey

### Getting Started

> **TODO:** Detailed installation steps to be added as implementation progresses.

**Prerequisites:**
- Red Hat OpenShift AI cluster with GPU nodes
- Access to model weights (downloadable for air-gapped deployment)
- A Git repository containing your legacy application

### Step 1: Point to Your Legacy Repo

Provide the Git repository URL and branch of the application you want to migrate. The system is language-agnostic -- it handles Python, Java, C++, and other languages found in legacy RHEL environments.

```
Input: https://github.com/your-org/legacy-app.git (branch: main)
```

You can index **multiple repositories** into the same knowledge graph, useful when a legacy system spans several repos.

### Step 2: Understand Your Codebase

Launch the **Code Understanding** notebook. The GraphRAG indexing process takes approximately one hour and builds a hierarchical knowledge graph of your entire codebase.

Once indexed, you can:
- **Run pre-canned reports** that answer common migration questions (deprecated APIs, dependency risks, migration complexity)
- **Ask ad-hoc questions** through the interactive GUI ("What does this module do?", "What depends on this library?", "What's the risk of upgrading this dependency?")

### Step 3: Generate a Migration Plan

The system produces a structured migration plan:
- Refactoring catalog with every required change
- Dependency upgrade path for RHEL 10 compatibility
- User stories organized by priority and dependency order
- Stories automatically created as Git issues on a Kanban board

**Review the plan before proceeding.** This is a key human-in-the-loop checkpoint.

### Step 4: Execute the Migration

Launch the **Code Migration** notebook. The agent mesh begins processing stories from the backlog:

1. Coding agent picks up a story, generates the refactored code
2. Evaluation agent creates a test suite verifying functional equivalence
3. CI agent bundles the changes into a pull request
4. If all checks pass, the PR is ready for review
5. If checks fail, the story moves to "blocked" for human input

### Step 5: Review and Merge

For each pull request:
- Review the generated code changes
- Verify the test suite covers the migration
- Check that functional equivalence is maintained (identical outputs for identical inputs)
- Merge approved PRs; send blocked items back to the backlog with guidance

## Requirements

### Minimum Hardware Requirements

- GPU nodes with sufficient VRAM for model serving:
  - gpt-oss-120B: requires multi-GPU setup (e.g., 2x L40S or equivalent)
  - Smaller models (Devstral, Ministral, e5-mistral): single GPU each
- Storage for GraphRAG index and model weights

### Minimum Software Requirements

- Red Hat OpenShift 4.17+
- Red Hat OpenShift AI (RHOAI)
- vLLM operator for model serving
- GPU Operator (NVIDIA)
- Git CLI

## What Gets Migrated

| Migration Type | Source | Target |
|---------------|--------|--------|
| **Python** | Python 2 | Python 3 |
| **Java** | OpenJDK/Corretto 7, 8, 11 | Java 17, 21, 25 |
| **C++** | Older GCC toolchains | Modern GCC on RHEL 10 |
| **System libraries** | OpenSSL 1.x, older systemd | OpenSSL 3.x, RHEL 10 systemd |
| **Package dependencies** | RHEL 7/8/9 packages | RHEL 10 equivalents |
| **Kernel compatibility** | Older kernel APIs | RHEL 10 kernel |

## Key Design Decisions

**Disconnected-first:** The entire system runs without internet access. All models, tools, and dependencies are bundled for air-gapped deployment. This is a baseline requirement, not an afterthought.

**Agents do the repetitive work, engineers do the architecture.** The system handles the mechanical translation -- deprecated API replacement, syntax updates, dependency resolution. Engineers focus on architectural decisions, oversight, agent evaluation, and exception handling.

**Traceability over black boxes.** While model inference is inherently opaque, the orchestration logic, agent code, outputs, and decision trails are fully traceable, auditable, and inspectable. This meets defense and government requirements for operationalized responsible AI.

**Multiple repos, one index.** Unlike tools bound to a single repository, the GraphRAG approach lets you index multiple repositories into a single knowledge graph. This is critical for legacy systems that span many repos.

**Bottom-up summarization.** The Leiden algorithm-based hierarchical summarization avoids the context window degradation problem. Instead of compacting and losing details as context fills up, the system builds understanding from the bottom up, preserving details that matter.

## Success Metrics

This engagement uses brownfield KPIs, not velocity metrics:

| Metric | What It Measures |
|--------|-----------------|
| **Functional correctness** | Identical outputs to the original given identical inputs |
| **Test coverage** | Target 80% coverage on migrated code |
| **Migration completion rate** | Percentage of stories completed without human intervention |
| **Developer confidence** | Time-to-contribution on migrated codebase |
| **Capacity gains** | Engineer-hours saved vs. manual migration estimate |

> "Velocity without correctness is not success -- it's technical debt generation at AI speed."

## References

- [Refactoring at Speed: An Agent Mesh Approach to Legacy System Modernization with Red Hat AI](https://www.redhat.com/en/blog/refactoring-speed-mission-agent-mesh-approach-legacy-system-modernization-red-hat-ai) -- Detailed technical blog post on the agent mesh architecture
- [GitHub Issue: RHEL 10 Modernization Agent Quickstart](https://github.com/rh-ai-quickstart/ai-quickstart-contrib/issues/44) -- Original quickstart proposal and requirements
- [GraphRAG (Microsoft)](https://github.com/microsoft/graphrag) -- The graph-based RAG framework used for code understanding
- [InstructLab](https://github.com/instructlab) -- Synthetic data generation toolkit
- [Red Hat OpenShift AI](https://www.redhat.com/en/technologies/cloud-computing/openshift/openshift-ai) -- AI/ML platform

## Tags

`rhel` `modernization` `migration` `agentic-ai` `graphrag` `legacy-code` `python2-to-python3` `java-migration` `disconnected` `air-gapped` `defense` `openshift-ai` `vllm` `code-refactoring`

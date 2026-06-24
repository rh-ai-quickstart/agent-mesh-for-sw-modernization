
** WORK IN PROGRESS - NOT READY FOR USE **

NOTES/QUESTIONS:
- why not build the current repo contents into the images as part of the docker build, avoids the later clone ?
- in -> Index a repository (Optional) would a pipeline add value or is having user do it manually better?

- [Detailed description](#detailed-description)
  - [Who is this for?](#who-is-this-for)
  - [Related content](#related-content)
  - [The business case for using agents in code modernization](#the-business-case-for-uses-agents-in-code-modernization)
  - [Example use cases](#example-use-cases)
  - [What this quickstart provides](#what-this-quickstart-provides)
  - [What you'll build](#what-youll-build)
  - [Architecture diagrams](#architecture-diagrams)
- [Requirements](#requirements)
  - [Minimum hardware requirements](#minimum-hardware-requirements)
  - [Minimum software requirements](#minimum-software-requirements)
  - [Required user permissions](#required-user-permissions)
- [Deploy](#deploy)
  - [Clone the repository](#clone-the-repository)
  - [Building the workbenches (Optional)](#building-the-workbenches-optional)
  - [Configuring model endpoints](#configuring-model-endpoints)
  - [Setting up the workbenches](#setting-up-the-workbenches)
  - [Index a repository (Optional)](#index-a-repository-optional)
    - [Saving and restoring an index](#saving-and-restoring-an-index)
  - [Interact with the code explorer](#interact-with-the-code-explorer)
  - [What you've accomplished](#what-youve-accomplished)
  - [Recommended next steps](#recommended-next-steps)
  - [Delete](#delete)
- [Technical details](#technical-details)
- [Tags](#tags)

## Detailed description

This quickstart demonstrates how to use GraphRAG to build a queryable knowledge graph from a legacy codebase, enabling developers and architects to ask natural language questions about code structure, dependencies, and migration risk without manually reading through thousands of files.

### Who is this for?

This quickstart is intended for:

- **Software architects** who need to quickly understand the structure and dependencies of an unfamiliar or legacy codebase
- **Development teams** planning a modernization or migration effort who need to identify high-risk components and recommended refactoring sequences
- **Platform engineers** running Red Hat OpenShift AI (RHOAI) who want to provide a self-service code comprehension tool to their teams

### Related content

- [Microsoft GraphRAG documentation](https://microsoft.github.io/graphrag)
- [LanceDB documentation](https://lancedb.github.io/lancedb)
- [Red Hat OpenShift AI documentation](https://docs.redhat.com/en/documentation/red_hat_openshift_ai_self-managed)
- [SDG Hub documentation](https://github.com/instructlab/sdg)

### The business case for uses agents in code modernization

Legacy codebases impose a significant "code comprehension tax" on engineering teams — time spent reading, tracing, and documenting code before any modernization work can begin. This tax grows with codebase size and age, and is compounded by staff turnover and missing documentation.

By indexing a codebase into a GraphRAG knowledge graph, teams can answer architectural questions in minutes rather than days, reduce onboarding time for new engineers, and make data-driven decisions about migration sequencing and risk — all without requiring deep familiarity with the code upfront.

### Example use cases

- **Migration planning**: Ask which modules are most tightly coupled and would be riskiest to refactor first
- **Dependency analysis**: Identify all modules that depend on a specific package or library
- **Vulnerability assessment**: Ask whether any dependencies have known security issues
- **Refactoring sequencing**: Get a recommended order for migrating components to minimize breaking changes
- **Ad-hoc exploration**: Ask any natural language question about the structure or behaviour of the codebase

### What this quickstart provides

- Pre-built workbench images for Data Generation and Data Indexing
- Pre-populated GraphRAG indexes for sample repositories stored under `indexes/`
- Jupyter notebooks for generating new indexes and querying existing ones
- A configurable pipeline that supports multiple repositories and iterative indexing runs

### What you'll build

By the end of this quickstart you will have:

- A running RHOAI workbench environment with the required dependencies installed
- A GraphRAG index of one or more codebases stored as parquet files under `indexes/`
- An interactive Jupyter notebook that lets you ask natural language questions about the indexed codebases

### Architecture diagrams

![Code Understanding](docs/images/Code%20Understanding.jpg)

## Requirements

### Minimum hardware requirements

| Resource | Minimum |
|---|---|
| CPU | 4 cores |
| Memory | 16 GB RAM |
| Storage | 50 GB (PVC) |
| GPU | Not required for querying; recommended for indexing large codebases |

### Minimum software requirements

- Red Hat OpenShift 4.12 or later
- Red Hat OpenShift AI (RHOAI) 2.8 or later
- Access to an OpenAI-compatible LLM endpoint for the GraphRAG chat model
- Access to an OpenAI-compatible embedding model endpoint
- Podman (for building workbench images)
- Access to an OCI-compatible image registry

### Required user permissions

- OpenShift project `edit` or `admin` role to create workbenches and PVCs
- RHOAI Data Science Project access to create and launch workbenches
- Read access to the target git repository to be indexed
- Push access to the OCI registry used to host workbench images (if building custom images)

## Deploy

### Clone the repository

```bash
git clone <this-repo-url>
cd <repo-name>
```

### Building the workbenches (Optional)

If you need to build the workbench images yourself you can run:

```bash
make build-and-push-all-images REGISTRY=<registry> VERSION=<version>
```

This is only necessary if you want to modify the images to add additional prerequisites.

### Configuring model endpoints

The indexing pipeline requires access to two OpenAI-compatible model endpoints — a chat LLM for entity extraction and community report generation, and an embedding model for generating vector embeddings.

1. Copy the environment template and fill in your model endpoint details:

   ```bash
   cp .env.template .env
   ```

   The variables to configure are:

   | Variable | Description |
   |---|---|
   | `GRAPHRAG_LLM_TOKEN` | API token for the GraphRAG chat model |
   | `GRAPHRAG_LLM_ID` | Model name (e.g. `gpt-oss-120b`) |
   | `GRAPHRAG_LLM_API_BASE` | Base URL of the chat model endpoint |
   | `GRAPHRAG_LLM_PROVIDER` | Provider name (e.g. `openai`) |
   | `GRAPHRAG_LLM_PROVIDER_GRAPHRAG` | Provider as used by GraphRAG (e.g. `openai_chat`) |
   | `EMBED_LLM_TOKEN` | API token for the embedding model |
   | `EMBED_LLM_ID` | Model name (e.g. `e5-mistral-7b-instruct`) |
   | `EMBED_LLM_API_BASE` | Base URL of the embedding model endpoint |
   | `EMBED_LLM_PROVIDER` | Provider name (e.g. `openai`) |
   | `EMBED_LLM_PROVIDER_GRAPHRAG` | Provider as used by GraphRAG (e.g. `openai_embedding`) |

   Recommended models:

   | Role | Model | Context size | Recommended GPU | Notes |
   |---|---|---|---|---|
   | GraphRAG chat | [`RedHatAI/gpt-oss-120b`](https://huggingface.co/RedHatAI/gpt-oss-120b) | 128k tokens | 4× H100 | Model weights alone require ~120GB (FP8); additional GPUs needed for 128k KV cache |
   | Embeddings | [`intfloat/e5-mistral-7b-instruct`](https://huggingface.co/intfloat/e5-mistral-7b-instruct) | 32k tokens | L40S | Context size drives KV cache memory beyond model weight footprint |

   Both models can be served via [vLLM](https://docs.vllm.ai) with an OpenAI-compatible endpoint.

   These values are stored in a Kubernetes Secret in your namespace by the `make install` target and are injected into the workbench pods at startup. They are never stored in the Helm chart or committed to the repository.

### Setting up the workbenches

1. Create the namespace:

   ```bash
   oc new-project <namespace>
   ```

2. Create the secret containing your model endpoint credentials:

   ```bash
   oc create secret generic code-understanding-env --from-env-file=.env -n <namespace>
   ```

3. Install the Helm chart. This creates the Data Science Project, shared PVC, and both workbenches, and automatically clones this repository into each workbench on startup. No cluster admin permissions are required.

   ```bash
   helm install code-understanding ./helm \
     --set registry=<registry> \
     --set version=<version> \
     --set namespace=<namespace> \
     --set repoUrl=<this-repo-url> \
     --set repoRef=<commit-or-branch>
   ```

   Alternatively, if you are running from a local clone of this repository, the following Makefile target will handle all steps above automatically, detecting the repo URL and current commit:

   ```bash
   make install REGISTRY=<registry> VERSION=<version> NAMESPACE=<namespace>
   ```

4. Launch each workbench:
   - In the RHOAI dashboard, navigate to **Data Science Projects** and select your project
   - Under the **Workbenches** tab you will see the `data-generation` and `data-indexing` workbenches created by the Helm chart
   - Click **Start** for each workbench, then click **Open** once it is running to open JupyterLab in your browser
   - This repository will already be cloned into the workbench home directory

### Index a repository (Optional)

Skip this section if you want to use the pre-populated indexes already included under `indexes/`.

1. From the **Data Generation** workbench, open `workflows/code_understanding/data_generation_graphrag_pipeline.ipynb`
2. Update the instance variables for your target repository:
   - `_GIT_REPO` — URL of the repository to index
   - `_GIT_BRANCH` — branch to clone
   - `_LANGUAGES` — list of languages to process. Supported values: `java`, `python`, `shell`, `sql`, `javascript`
3. Run the notebook — enriched `.txt` files will be written to the `target/` directory

4. From the **Data Indexing** workbench, open `workflows/code_understanding/data_indexing_graphrag_pipeline.ipynb`
5. Update `_GRAPHRAG_SOURCE_PATH` to point to your desired output directory under `indexes/`
6. Run the notebook — parquet files will be written to `indexes/<repo-name>/source/output/`

#### Saving and restoring an index

Once an index has been generated you can save it to your local machine for reuse across installs using the JupyterLab file browser:

**To download an index:**
1. In the JupyterLab file browser, navigate to `indexes/<repo-name>/source/output/`
2. Select all parquet files, right-click and select **Download**
3. Store them locally under a folder named `<repo-name>/source/output/`

**To upload a previously saved index:**
1. In the JupyterLab file browser, navigate to `indexes/` and create a folder named `<repo-name>/source/output/`
2. Navigate into that folder, right-click and select **Upload Files**
3. Select the parquet files from your local machine
4. The index is now available for querying — proceed to [Interact with the code explorer](#interact-with-the-code-explorer)

### Interact with the code explorer

1. From the **Data Indexing** workbench, open `workflows/code_understanding/data_analysis_graphrag_pipeline.ipynb`
2. Set `_GRAPHRAG_SOURCE_PATH` to point to the index you want to query — for a pre-populated index this will be `indexes/<repo-name>/source`, for a self-generated index this will be the path you set for `_GRAPHRAG_SOURCE_PATH` in the Data Indexing notebook (e.g. `indexes/<repo-name>/source`)
3. Run the notebook
4. In the **Ad-Hoc Queries** section, update the `question` variable with your question and run the cell

Example questions:
- `Which modules would be riskiest to refactor first? Include the fully qualified names.`
- `What migration order would be recommended when refactoring to reduce breaking changes?`
- `Are there any vulnerable dependencies or libraries?`

### What you've accomplished

- Set up RHOAI workbenches with the required dependencies for GraphRAG-based code analysis
- Loaded a pre-populated (or self-generated) GraphRAG index of a legacy codebase
- Used natural language queries to explore the structure, dependencies, and migration risk of the codebase

### Recommended next steps

- Index additional repositories by repeating the Data Generation and Data Indexing steps with a new `_GRAPHRAG_SOURCE_PATH`
- Explore the Code Migration workflow to generate refactored code, documentation, and tests based on the insights from the code explorer
- Integrate the parquet files into a CI/CD pipeline to keep the index up to date as the codebase evolves

### Delete

To remove the workbenches, PVC, and Data Science Project:

```bash
make uninstall NAMESPACE=<namespace>
```

Or manually:

```bash
helm uninstall code-understanding --namespace <namespace>
```

## Technical details

The code understanding pipeline is built on [Microsoft GraphRAG](https://microsoft.github.io/graphrag), which constructs a hierarchical knowledge graph from a corpus of text documents. In this case, the corpus is the enriched `.txt` representations of source code files, with metadata comments prepended to each file by the Data Generation step.

GraphRAG extracts entities (classes, functions, packages, dependencies), relationships between them, and groups them into communities using graph clustering. It then generates LLM-summarized community reports that capture the high-level purpose and relationships of each cluster. These community reports are stored as parquet files and are the primary data source for global search queries.

Global search — used exclusively in this quickstart — works by mapping a natural language question across the community reports and reducing the results into a single synthesised answer. It does not perform vector similarity search, so the LanceDB vector store built during indexing is not required for querying.

The parquet files produced by indexing are:

| File | Contents |
|---|---|
| `entities.parquet` | Extracted code entities (classes, functions, packages, etc.) |
| `relationships.parquet` | Directed relationships between entities |
| `communities.parquet` | Graph community assignments |
| `community_reports.parquet` | LLM-generated summaries of each community |
| `text_units.parquet` | Source text chunks used during indexing |

## Tags

* **Title:** Code Understanding with GraphRAG
* **Description:** Index a legacy codebase into a GraphRAG knowledge graph and ask natural language questions about its structure, dependencies, and migration risk — deployed as RHOAI workbenches via Helm.
* **Industry:** Adopt and scale AI
* **Product:** OpenShift AI
* **Use case:** Agentic software and system modernization
* **Contributor org:** Red Hat



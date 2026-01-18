# App Overview: Cognitive Research Platform

## Purpose
The application is a **Cognitive Research Platform** designed to assist researchers in analyzing interview transcripts and text data. Unlike traditional tools, it doesn't just store data; it **actively participates** in the analysis using Graph Data Science and Semantic Discovery.

**Key Goals:**
- **Organize**: Manage research projects and interview files.
- **Analyze**: Apply coding (open, axial) to text fragments using **AI assistance**.
- **Synthesize**: Identify core themes ("Nucleo") using **Graph Algorithms**.
- **Discover**: Find hidden connections using **Semantic Triangulation**.
- **Report**: Generate integrated reports.

## Architecture: The "Cognitive Loop"

The system is designed as a feedback loop where analysis feeds the graph, and the graph grounds future analysis.

### 1. The "Brain" (Python Backend)
- **Framework**: FastAPI (`backend/app.py`).
- **Async Processing**: **Celery + Redis** handles heavy AI tasks across distributed workers.
- **Cognitive Engines**:
    - **Vector Engine (Qdrant)**: Handles "Meaning". Enables **Discovery Search** (Pos/Neg examples) and Code Suggestions.
    - **Graph Engine (Neo4j)**: Handles "Structure". Runs **GDS Algorithms** (PageRank, Louvain) to persist centrality and communities.
    - **Relational Engine (Postgres)**: Handles "Truth" (Raw text, metadata).

### 2. The Workflow (Stages)
The app enforces a sequential workflow enriched by AI:
1.  **Ingestion**: Reading files, chunking, and indexing.
2.  **Coding**: Assigning "codes". The system **suggests codes** based on similarity.
3.  **Axial**: Analyzing relationships. User runs **GDS** to detect communities automatically.
4.  **Nucleus**: Identifying central themes.
5.  **Reflexivity**: The system acts as a **GraphRAG** agent, answering questions with full context.

### 3. The Interface (Frontend)
- **Tech**: React + Vite + TailwindCSS.
- **Interactive Visualization**: Uses `react-force-graph-2d` for the **Living Graph** (Nodes colored by Community, sized by Centrality).
- **Communication**: REST API with strict TypeScript contracts.

## Data Flow Example (Cognitive Analysis)
1.  User clicks "Analyze" on an interview file.
2.  **Context Injection**: The backend queries the **Graph** to understand current themes ("Safety", "Violence").
3.  **LLM Processing**: GPT-5 receives the interview text + the **Graph Context**.
4.  **Synthesis**: The LLM analyzes the text *aligned* with the existing theory.
5.  **Persistence**: New codes are written to the Graph.
6.  **Update**: User runs "Calculate GDS"; the new nodes update the global metrics (PageRank), refining the context for the *next* analysis.

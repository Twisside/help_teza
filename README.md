# Local RAG Assistant

A local Retrieval-Augmented Generation (RAG) system for knowledge management with AI-powered search and chat.

> University thesis project.

## Features

- **Document Indexing** - Upload and index documents (PDF, CSV, code files, plain text)
- **AI Q&A** - Ask questions and get answers grounded in your documents
- **Chat Sessions** - Multi-turn conversations with context awareness
- **Background Indexing** - Index entire folders automatically with CPU/RAM throttling
- **Time-Aware Queries** - Natural date references ("yesterday", "next Monday") resolved automatically
- **Tag Generation** - Automatic content tagging via LLM

## Tech Stack

- **Backend:** Python, Flask
- **LLM/Embeddings:** LM Studio (Gemma-300M)
- **Vector Database:** Qdrant
- **Code Parsing:** Tree-sitter (AST-based chunking)
- **UI:** Vanilla HTML/JS with jQuery, jsTree

## Prerequisites

- Python 3.10+
- LM Studio (running locally)
- Qdrant (running locally or Docker)

## Running the Application

### 1. Install LM Studio

Download and install LM Studio from [lmstudio.ai](https://lmstudio.ai).

### 2. Download Models

Use the `lms` CLI to download the required model and embedding model:

```bash
# Download the chat model (e.g., Gemma-300M or your preferred model)
lms get "gemma-3-1b"

# Download the embedding model
lms get "text-embedding-embeddinggemma-300m"
```

Or use the LM Studio GUI to download models from the Discover section.



### 4. Install Dependencies and Run

```bash
pip install -r requirements.txt
python main.py
```

The app will be available at `http://localhost:5001`

## Project Structure

```
help_teza/
├── main.py                  Flask app entry point, routes,
├── database.py              Qdrant vector storage & retrieval
├── chunker.py               Document chunking (paragraph + Tree-sitter)
├── document_parser.py      File format routing
├── embedding.py             LM Studio embedding service
├── chat_handle.py          Chat session management
├── preprocessor.py         Time-aware query preprocessing
├── index_worker.py         Background folder indexer
├── file_manager.py         Directory traversal
├── tag_generation.py       LLM-based tag generation
├── templates/
│   └── home.html           Main UI
├── docs/
│   └── diagrams/           PlantUML UML diagrams
└── uploads/                User-uploaded files
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/upload` | POST | Upload single file |
| `/ask` | POST | Ask a question |
| `/api/chat/ask` | POST | Chat message |
| `/api/chat/history` | GET | Get chat history |
| `/api/chat/clear` | POST | Clear chat session |
| `/api/index_directories` | POST | Index selected folders |
| `/api/indexer_status` | GET | Get indexer status |
| `/api/toggle_pause` | POST | Pause/resume indexer |
| `/api/models` | GET | List available models |
| `/api/models` | PATCH | Switch model |

## Key Design Decisions

1. **Hybrid Chunker** - Combines paragraph-based chunking for natural language with Tree-sitter AST parsing for code files
2. **Qdrant over ChromaDB** - Faster, more accurate at any volume
3. **Context Window** - Last 10 messages kept in memory; older messages archived to Qdrant for long-term context
4. **CPU/RAM Throttling** - Background indexer respects 30% CPU / 80% RAM thresholds

## UML Diagrams

See `docs/diagrams/` for PlantUML diagrams covering:
- Sequence diagrams for all major workflows
- Activity diagrams for all major workflows
- Class diagram for core domain model

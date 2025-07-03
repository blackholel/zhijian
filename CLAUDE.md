# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Yuxi-Know (语析) is an AI-powered knowledge management platform that combines Large Language Models with Retrieval-Augmented Generation (RAG) and Knowledge Graph technologies. The system provides conversational AI with document processing, intelligent agents, and multi-modal capabilities.

## Development Commands

### Starting the Development Environment
```bash
# Start all services (web, API, databases)
docker compose up --build

# Start in background
docker compose up --build -d

# View API logs
docker logs api-dev -f

# Stop all services
docker compose down
```

### Access Points
- Web Application: http://localhost:5173
- API Documentation: http://localhost:5050/docs
- Neo4j Browser: http://localhost:7474
- MinIO Console: http://localhost:9001 (admin/minioadmin)

### Frontend Development (web/)
```bash
# Install dependencies
pnpm install

# Development server
pnpm dev

# Build for production
pnpm build

# Type checking
pnpm type-check

# Linting
pnpm lint
```

### Backend Development
```bash
# Run API server directly (requires environment setup)
python server/main.py

# Run tests
python -m pytest test/

# Check specific functionality
python test/test_neo4j.py
```

## Architecture Overview

### Core Components
- **server/**: FastAPI backend with authentication, chat, and graph APIs
- **src/**: Core application logic including agents, models, and plugins
- **web/**: Vue.js frontend with graph visualization and chat interface
- **docker/**: Container configurations and initialization scripts

### Key Technologies
- **Backend**: FastAPI, LangChain/LangGraph, LlamaIndex, LightRAG
- **Frontend**: Vue.js 3, Ant Design Vue, Vite, Pinia, Sigma.js
- **Databases**: Neo4j (graph), PostgreSQL (metadata), Milvus (vectors)
- **AI/ML**: Multiple LLM providers, BGE-M3 embeddings, OCR processing

### Agent System
The platform uses a plugin-based agent architecture with LangGraph:
- **Agents**: Located in `src/agents/` with configurable workflows
- **Tools**: Extensible tool system including web search, knowledge base, and calculator
- **Configuration**: Agent behavior controlled via configuration files

### Knowledge Management
- **RAG Pipeline**: Document ingestion → OCR processing → Vector embeddings → Retrieval
- **Knowledge Graphs**: Neo4j for structured data with entity relationships
- **Multi-Modal**: Support for PDFs, images, and text with MinerU and PaddleOCR

## Environment Setup

### Required Configuration
Create `src/.env` file with at minimum:
```
SILICONFLOW_API_KEY=your_api_key
```

### Optional Configuration
```
TAVILY_API_KEY=your_tavily_key  # For web search
OPENAI_API_KEY=your_openai_key  # For OpenAI models
DEEPSEEK_API_KEY=your_deepseek_key  # For DeepSeek models
```

### Model Providers
- **Default**: SiliconFlow (free tier available)
- **Supported**: OpenAI, DeepSeek, Zhipu AI, Dashscope, Together.ai
- **Local**: VLLM and Ollama integration
- **Configuration**: Edit `src/static/models.yaml` for custom models

## Database Management

### Neo4j Graph Database
- **Access**: http://localhost:7474 (neo4j/neo4j-password)
- **Connection**: bolt://localhost:7687
- **Purpose**: Knowledge graph storage and entity relationships

### PostgreSQL
- **Access**: localhost:5432 (yuxi_user/yuxi_password)
- **Extensions**: pgvector for vector operations, Apache AGE for graph queries
- **Purpose**: User data, conversation history, document metadata

### Milvus Vector Database
- **Access**: localhost:19530
- **Purpose**: Vector embeddings storage and similarity search
- **Configuration**: Automatic collection creation and indexing

## Key Development Patterns

### Backend API Development
- Use FastAPI with async/await patterns
- Authentication middleware in `server/utils/auth_middleware.py`
- Database models in `server/models/`
- API routes in `server/routers/`

### Frontend Component Development
- Vue.js 3 with Composition API
- Pinia stores for state management in `web/src/stores/`
- Component organization in `web/src/components/`
- API clients in `web/src/apis/`

### Agent Development
- Extend base agent classes in `src/agents/`
- Define tools in `src/agents/tools_factory.py`
- Configure agent behavior in configuration files
- Use LangGraph for workflow orchestration

### Plugin Development
- Document processing plugins in `src/plugins/`
- OCR capabilities with MinerU and PaddleOCR
- Extend tool functionality through plugin system

## Common Development Tasks

### Adding New LLM Providers
1. Update `src/static/models.yaml` with model configurations
2. Add provider credentials to environment variables
3. Update frontend model selector in `web/src/components/ModelSelectorComponent.vue`

### Adding New Agent Tools
1. Implement tool in `src/agents/tools_factory.py`
2. Register tool in agent configuration
3. Add tool result renderer in `web/src/components/ToolCallingResult/`

### Database Schema Changes
1. Update models in `server/models/`
2. Create migration scripts if needed
3. Update API endpoints in `server/routers/`

## Debugging and Monitoring

### Log Locations
- API logs: `docker logs api-dev`
- Web logs: Browser console
- Database logs: Individual container logs

### Common Issues
- **Port conflicts**: Ensure ports 5173, 5050, 7474, 9000, 19530, 5432 are available
- **Memory issues**: Vector operations require sufficient RAM
- **GPU support**: NVIDIA Container Toolkit required for GPU features

### Performance Monitoring
- Neo4j browser for graph query performance
- Milvus metrics for vector search performance
- FastAPI automatic documentation for API debugging
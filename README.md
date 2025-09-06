# AGNO Insiders App

A Python AI-based application to identify and collect information about relevant subjects (insiders) of Italian companies by automatically analyzing corporate governance reports.

The execution flow includes the following steps:

1. Agentic search for the most recent available corporate governance report
2. Extraction, chunking, and processing of the extracted text via an LLM
3. Preliminary filtering and duplicate removal
4. Final validation via an LLM

## 🚀 Installation

### Prerequisites

- Python 3.12 or newer
- [uv](https://docs.astral.sh/uv/) for dependency management

### Setup

1. **Clone the repository**:

   ```bash
   git clone <repository-url>
   cd agno-insiders-app
   ```

2. **Install dependencies**:

   ```bash
   uv sync
   uv run crawl4ai-setup
   sudo apt install libmagic-dev poppler-utils tesseract-ocr
   ```

3. **Configure environment variables**:
   Create a `.env` file in the project root:

   ```env
   # Google Gemini API Key (required)
   GOOGLE_API_KEY=your_google_api_key_here

   # Neo4j Database connection settings
   NEO4J_URI=your_neo4j_uri
   NEO4J_USERNAME=your_neo4j_username
   NEO4J_PASSWORD=your_neo4j_password
   ```

## 📖 Usage

```bash
uv run main.py -c "company_name"
```

If you prefer to skip the report search, you can provide the link directly:

```bash
uv run main.py -report_url "report_url"
```

## 📋 Main Dependencies

- **agno**: Framework for AI agents and workflows
- **google-genai**: Integration with Google's Gemini models
- **crawl4ai**: Advanced web crawling
- **pydantic**: Data validation and serialization
- **unsdtructured**: PDF document processing and chunking

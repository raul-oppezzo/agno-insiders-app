# AGNO Insiders App

Un'applicazione Python basata su AI per identificare e raccogliere informazioni sui soggetti rilevanti (insiders) delle aziende italiane attraverso l'analisi automatica di report di governance e ricerche web.

## 🚀 Installazione

### Prerequisiti

- Python 3.12 o superiore
- [uv](https://docs.astral.sh/uv/) per la gestione delle dipendenze

### Setup

1. **Clona il repository**:

   ```bash
   git clone <repository-url>
   cd agno-insiders-app
   ```

2. **Installa le dipendenze**:

   ```bash
   uv sync
   uv run crawl4ai-setup
   sudo apt install libmagic-dev poppler-utils tesseract-ocr
   ```

3. **Configura le variabili d'ambiente**:
   Crea un file `.env` nella root del progetto:

   ```env
   # API Key per Google Gemini (richiesta)
   GOOGLE_API_KEY=your_google_api_key_here

   # Chunk settings
   CHUNK_MAX_CHARACTERS=50000
   CHUNK_OVERLAP=100

   # Debug
   DEBUG=false
   ```

## 📖 Utilizzo

    ```bash
    uv run main.py -c "company_name"
    ```

## 📋 Dipendenze Principali

- **agno**: Framework per agenti AI e workflow
- **google-genai**: Integrazione con modelli Gemini di Google
- **crawl4ai**: Web crawling avanzato
- **pydantic**: Validazione e serializzazione dati
- **unsdtructured**: Elaborazione documenti PDF e chunking

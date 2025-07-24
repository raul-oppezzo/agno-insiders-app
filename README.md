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
   ```

3. **Configura le variabili d'ambiente**:
   Crea un file `.env` nella root del progetto:
   ```env
   # API Key per Google Gemini (richiesta)
   GOOGLE_API_KEY=your_google_api_key_here
   ```

## 📖 Utilizzo

    ```bash
    cd src
    uv run main.py --company_name=company_name
    ```

## 📋 Dipendenze Principali

- **agno**: Framework per agenti AI e workflow
- **google-genai**: Integrazione con modelli Gemini di Google
- **crawl4ai**: Web crawling avanzato
- **pydantic**: Validazione e serializzazione dati
- **pypdf2**: Elaborazione documenti PDF

# YouTube Analyzer

FastAPI backend + minimal frontend that fetches a YouTube transcript, analyzes it against your stored personal context with Claude (`claude-sonnet-4-5`), and produces a flowing **delivery script** you can use when sharing the ideas with others.

## Features

- Paste a YouTube URL or 11-character video ID
- Pulls the transcript via `youtube-transcript-api`
- Sends transcript + your personal context to Claude
- Returns four sections: **Summary**, **Key Insights**, **Personal Relevance**, **Delivery Script** (Hook · Context · Core Idea · Personal Tie · Call to Action)
- Editable personal context stored locally in `context_data.json`

## Project structure

```
youtube-analyzer/
├── main.py
├── services/
│   ├── transcript.py
│   ├── context.py
│   └── claude.py
├── frontend/
│   └── index.html
├── context_data.json
├── requirements.txt
├── .env.example
└── README.md
```

## Setup

1. **Clone / cd into the project**
   ```bash
   cd youtube-analyzer
   ```

2. **Create a virtual environment**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure your API key**
   ```bash
   cp .env.example .env
   # then edit .env and set ANTHROPIC_API_KEY=sk-ant-...
   ```

5. **Run the server**
   ```bash
   uvicorn main:app --reload --port 8000
   ```

6. **Open the UI**
   - http://localhost:8000

## API endpoints

| Method | Path        | Description                                                                          |
|--------|-------------|--------------------------------------------------------------------------------------|
| GET    | `/health`   | Health check                                                                         |
| POST   | `/analyze`  | Body: `{url, length, context}` — returns the full analysis. Stateless (no DB).       |

The personal context, library of analyzed videos, ratings, notes, and tags all live in the visitor's browser (`localStorage`). Each visitor has their own private library — nothing is stored on the server. This makes the app safe to host publicly.

### Example: analyze a video

```bash
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"url":"https://www.youtube.com/watch?v=dQw4w9WgXcQ"}'
```

### Example: update context

```bash
curl -X POST http://localhost:8000/context \
  -H "Content-Type: application/json" \
  -d '{"category":"current_goals","value":"Ship a personal website and learn ML fundamentals."}'
```

Or update all at once:

```bash
curl -X POST http://localhost:8000/context \
  -H "Content-Type: application/json" \
  -d '{"values":{"career":"...", "values":"...", "current_goals":"..."}}'
```

## Notes

- Personal context categories: `career`, `values`, `current_goals`, `relationships`, `interests`, `challenges`, `background`.
- The `delivery_script` keeps a fixed structure (Hook → Context → Core Idea → Personal Tie → Call to Action) but the words and personal tie change every run based on the video and your context.
- CORS is enabled for all origins so you can call the API from other tools too.

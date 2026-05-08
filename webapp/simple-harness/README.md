# Simple Browser-Harness Web Service 🧠💻

A minimalist web interface that wraps the `browser-harness` with a CLI-like experience. It streams real-time logs and screenshots as the agent "thinks" and "acts".

## Prerequisites

1. **Chrome with Remote Debugging**:
   ```bash
   /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
     --remote-debugging-port=9222 \
     --user-data-dir=/tmp/chrome-debug
   ```

2. **Gemini API Key**:
   Create a `.env` file in `backend/` with your key:
   ```env
   GEMINI_API_KEY=your-api-key-here
   ```

## Running the Service

```bash
cd webapp/simple-harness/backend
uv run python main.py
```

Open **`http://localhost:8000`** in your browser.

## Accessibility Testing

The project includes a suite of automated tests that simulate users with different disabilities:

```bash
cd webapp/simple-harness/tests
python disability_tests.py
```

These tests verify that the agent provides appropriate descriptive feedback, visual logs, and precise actions for various personas.

## Features

- **CLI-like Logs**: See every step of the agent's reasoning.
- **Live Viewport**: Watch the browser screenshot update after every action.
- **Self-Healing**: Inherits the harness's technical self-healing and uses a cognitive loop for task recovery.
- **Minimalist Design**: Clean, dark-mode UI for distraction-free automation.

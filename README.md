# Chatbot QA Automation Platform

A local web application for automated testing of website chatbots using Playwright.

## Features

- 🤖 **Automated Chatbot Testing** - Send test utterances and capture bot responses
- ⚡ **Real-time Metrics** - Track response latency and self-service rate
- 📊 **Live Dashboard** - Poll results every 2 seconds during tests
- 🔧 **Configurable Selectors** - Customize CSS selectors for any chatbot widget
- 🔐 **Login Support** - Handle authenticated chatbot interfaces

## Tech Stack

- **Frontend**: React + Vite + TypeScript + Tailwind CSS
- **Backend**: Python FastAPI + SQLModel + Playwright
- **Database**: SQLite

## Quick Start

### 1. Backend Setup

```bash
cd backend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt

# Install Playwright browser
playwright install chromium

# Start the server
uvicorn main:app --reload --port 8000
```

### 2. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start dev server
npm run dev
```

### 3. Open the App

Navigate to [http://localhost:5173](http://localhost:5173)

## Usage

1. Enter the **Target URL** of the website with the chatbot
2. (Optional) Enter **login credentials** if the chatbot requires authentication
3. Enter **Test Questions** - one question per line
4. Click **RUN TEST**
5. Watch the results populate in real-time

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/start-test` | POST | Start a new test run |
| `/api/results` | GET | Get test results |
| `/api/test-runs` | GET | List all test runs |

## Metrics

- **Avg Response Time**: Average time for bot to respond (ms)
- **Self-Service Rate**: Percentage of queries resolved without human escalation
- **Passed/Escalated**: Count of successful vs. escalated conversations

## License

MIT

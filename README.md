# Vera AI Merchant Engagement Bot

An AI-powered merchant engagement bot built for the **magicpin AI Challenge** using **FastAPI** and **Groq Llama 3.3 70B**.

The bot generates personalized WhatsApp messages by combining merchant, category, customer, and trigger context while maintaining conversation state throughout the interaction.

---

## Features

- AI-powered personalized WhatsApp message generation
- Context-aware responses using merchant, customer, category, and trigger data
- Stateful conversation management
- Auto-reply detection
- Intent transition handling
- Anti-repetition message generation
- Trigger suppression to prevent duplicate outreach
- Deterministic responses (`temperature = 0`)
- REST API built with FastAPI
- Compatible with the official Judge Simulator

---

## Tech Stack

- Python 3.12
- FastAPI
- Uvicorn
- Groq API
- Llama 3.3 70B Versatile
- Pydantic
- python-dotenv

---

## Project Structure

```text
magicpin-vera-bot/
│
├── dataset/
│   ├── categories/
│   ├── customers_seed.json
│   ├── merchants_seed.json
│   └── triggers_seed.json
│
├── examples/
│
├── .env
├── .gitignore
├── bot.py
├── judge_simulator.py
├── test_api.py
├── requirements.txt
├── README.md
├── challenge-brief.md
├── challenge-testing-brief.md
├── engagement-design.md
└── engagement-research.md
```

---

# Installation

## Clone the repository

```cmd
git clone <your-github-repository-url>
cd magicpin-vera-bot
```

## Create a virtual environment

```cmd
python -m venv venv
```

## Activate the virtual environment

```cmd
venv\Scripts\activate
```

## Install dependencies

```cmd
pip install -r requirements.txt
```

---

# Environment Variables

Create a `.env` file in the project root.

```env
GROQ_API_KEY=your_groq_api_key
```

---

# Running the Bot

Start the FastAPI server.

```cmd
uvicorn bot:app --host 0.0.0.0 --port 8080
```

The bot will be available at:

```
http://localhost:8080
```

---

# API Endpoints

| Method | Endpoint | Description |
|---------|----------|-------------|
| GET | `/v1/healthz` | Health check |
| GET | `/v1/metadata` | Bot metadata |
| POST | `/v1/context` | Store category, merchant, customer and trigger context |
| POST | `/v1/tick` | Generate outbound AI messages |
| POST | `/v1/reply` | Continue an existing conversation |
| POST | `/v1/teardown` | Clear in-memory state |

---

# Running the Judge Simulator

Update the configuration in `judge_simulator.py`.

```python
BOT_URL = "http://localhost:8080"
LLM_PROVIDER = "groq"
LLM_MODEL = "llama-3.3-70b-versatile"
```

Run the simulator.

```cmd
python judge_simulator.py
```

The simulator validates:

- Health endpoint
- Metadata endpoint
- Context ingestion
- Auto-reply detection
- Intent transition
- Hostile message handling

---

# Design Highlights

- Uses **Groq Llama 3.3 70B Versatile** for message generation.
- Deterministic outputs using `temperature = 0`.
- Maintains conversation history in memory.
- Detects automated replies before continuing conversations.
- Prevents duplicate trigger execution through suppression keys.
- Avoids repeating previously generated messages.
- Switches directly to action mode after explicit merchant confirmation.
- Handles hostile or opt-out responses gracefully.

---

# Deployment
The application is deployed on **Render**.
---

# Requirements

```
fastapi==0.116.1
uvicorn==0.35.0
groq==0.31.0
python-dotenv==1.1.1
pydantic==2.11.7
```

---

# License

This project was developed for the **magicpin AI Challenge** for educational and evaluation purposes.
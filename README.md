# Weekend Wizard - AI Agent Capstone Project

A friendly CLI agent that plans weekend activities using MCP tools and local LLM inference.

## Overview

Weekend Wizard is a complete AI agent implementation demonstrating:
- **ReAct pattern**: Step-by-step reasoning and action selection
- **MCP integration**: Tools exposed via Model Context Protocol
- **Tool use**: Weather, books, jokes, and dog photos via free APIs
- **Reflection**: Self-correction before final response
- **Local inference**: Runs on Ollama with Mistral 7B (no API costs)

## What It Does

Given a user prompt like:
> "Plan a cozy Saturday in New York at (40.7128, -74.0060). Include the current weather, 2 book ideas about mystery, one joke, and a dog pic."

The agent will:
1. **Reason** about what tools it needs
2. **Call** the weather API for current conditions
3. **Call** the book API for mystery recommendations
4. **Call** the joke API for a one-liner
5. **Call** the dog API for a random image
6. **Reflect** on whether it has everything needed
7. **Respond** with an upbeat, personalized plan

## Project Structure

```
weekend-wizard/
├── README.md                # This file
├── OLLAMA_INSTALL_GUIDE.md  # Ollama setup instructions
├── server_fun.py            # MCP server with tools
├── agent_fun.py             # Agent client with ReAct loop
├── DemoTranscript.txt       # Sample session transcript
├── .gitignore               # Git ignore file
└── requirements.txt         # Python dependencies
```

## Prerequisites

- Python 3.10+
- Ollama (local LLM runtime)
- ~8GB RAM minimum (for 7B models)

## Installation

### 1. Install Ollama

Download from [ollama.com/download](https://ollama.com/download) and install.

### 2. Pull a Model

```bash
ollama pull mistral:7b
```

Optional: Try other models
```bash
ollama pull llama3.2:3b    # Smaller, faster
ollama pull qwen2.5:7b     # Good instruction following
```

### 3. Clone/Copy Project Files

```bash
mkdir weekend-wizard
cd weekend-wizard
# Copy server_fun.py and agent_fun.py to this directory
```

### 4. Create Virtual Environment

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# macOS/Linux
python -m venv .venv
source .venv/bin/activate
```

### 5. Install Dependencies

```bash
pip install mcp>=1.2 requests ollama
```

Or create a `requirements.txt`:
```
mcp>=1.2
requests>=2.31.0
ollama>=0.1.0
```

Then run: `pip install -r requirements.txt`

## Running the Agent

### Start the Agent

```bash
python agent_fun.py
```

The agent will:
1. Start the MCP server (`server_fun.py`)
2. Connect and list available tools
3. Wait for your input


## Understanding the Code

### Server (`server_fun.py`)

The MCP server exposes 6 tools:

1. **city_to_coords(city)** - Open-Meteo Geocoding API for city-to-coordinates (Stretch Goal 1)
2. **get_weather(lat, lon)** - Open-Meteo API for current weather
3. **book_recs(topic, limit)** - Open Library API for book suggestions
4. **random_joke()** - JokeAPI for safe one-liners
5. **random_dog()** - Dog CEO API for random dog images
6. **trivia()** - Open Trivia DB for quiz questions (optional)

Each tool:
- Has type-annotated parameters
- Includes a docstring (used as description)
- Handles HTTP errors gracefully
- Returns structured data (dicts/lists)

The agent implements a **ReAct loop** with reflection:

1. **Setup**: Connects to MCP server, discovers tools
2. **Loop**: For each user query:
   - Sends conversation history to LLM
   - LLM decides: call tool or provide final answer
   - If tool call: execute, observe result, continue loop
   - If final answer: proceed to reflection
3. **Reflection**: One-shot check for mistakes or missing tool calls
4. **Output**: Final answer to user

**Key Design Decisions:**
- JSON-only output from LLM for structured parsing
- Safety loop (max 8 iterations) to prevent infinite loops
- Temperature 0.2 for deterministic tool selection
- Reflection step 
- Colored terminal output for visual clarity during the ReAct loop
- Tool call timing to show API latency awareness
- `/help`, `/tools`, and other commands 

"""
MCP Agent Client for Weekend Wizard
Implements ReAct pattern with reflection for reliable tool use.
"""

import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from ollama import chat

# ---------------------------------------------------------------------------
# Terminal colors 
# ---------------------------------------------------------------------------
if sys.platform == "win32":
    os.system("")  # Enable ANSI escape sequences on Windows

if os.environ.get("NO_COLOR") or not sys.stdout.isatty():
    C_RESET = C_BOLD = C_DIM = C_RED = C_GREEN = C_YELLOW = C_CYAN = C_MAGENTA = ""
else:
    C_RESET = "\033[0m"
    C_BOLD = "\033[1m"
    C_DIM = "\033[2m"
    C_RED = "\033[31m"
    C_GREEN = "\033[32m"
    C_YELLOW = "\033[33m"
    C_CYAN = "\033[36m"
    C_MAGENTA = "\033[35m"

# ---------------------------------------------------------------------------
# Model configuration — Stretch Goal: experiment with temperature & top_p
# ---------------------------------------------------------------------------
MODEL_NAME = "mistral:7b"

# Temperature controls randomness (0.0 = deterministic, 1.0 = very creative).
# top_p (nucleus sampling) limits the token pool (lower = more focused).
#
# We use different settings for different phases of the agent loop:
#   - Tool selection needs LOW temperature for reliable, parseable JSON output.
#   - Final answer benefits from SLIGHTLY higher temperature for personality.
#   - Reflection needs LOW temperature for precise, objective quality checks.
#   - JSON repair needs ZERO temperature for maximum compliance.


TOOL_TEMPERATURE = 0.2     # Low: reliable JSON + consistent tool choices
TOOL_TOP_P = 0.9           # Moderate: allow some variety in phrasing

ANSWER_TEMPERATURE = 0.4   # Slightly warmer: friendlier, more natural answers
ANSWER_TOP_P = 0.95        # Wider: more creative word choices

REFLECTION_TEMPERATURE = 0  # Cold: precise, objective quality checking
REFLECTION_TOP_P = 0.9

REPAIR_TEMPERATURE = 0     # Coldest: maximum compliance for JSON repair
REPAIR_TOP_P = 0.5         # Tight: only the most likely tokens

# ---------------------------------------------------------------------------
# Stretch Goal: User preferences — persist favorites across sessions
# ---------------------------------------------------------------------------
PREFS_FILE = Path(__file__).parent / "preferences.json"

DEFAULT_PREFS = {
    "default_city": None,
    "favorite_genres": [],
    "name": None,
}


def load_preferences() -> Dict[str, Any]:
    """Load user preferences from local JSON file, or return defaults."""
    if PREFS_FILE.exists():
        try:
            with open(PREFS_FILE, "r") as f:
                saved = json.load(f)
            # Merge with defaults so new keys are always present
            merged = {**DEFAULT_PREFS, **saved}
            return merged
        except (json.JSONDecodeError, IOError):
            pass
    return dict(DEFAULT_PREFS)


def save_preferences(prefs: Dict[str, Any]) -> None:
    """Save user preferences to local JSON file."""
    with open(PREFS_FILE, "w") as f:
        json.dump(prefs, f, indent=2)
    print(f"  {C_DIM}[preferences saved to {PREFS_FILE.name}]{C_RESET}")


def prefs_to_prompt_section(prefs: Dict[str, Any]) -> str:
    """Convert preferences into a system prompt section the LLM can use."""
    lines = []
    if prefs.get("name"):
        lines.append(f"- The user's name is {prefs['name']}. Greet them by name.")
    if prefs.get("default_city"):
        lines.append(
            f"- Default city: {prefs['default_city']}. "
            "If the user doesn't specify a location, use city_to_coords with this city."
        )
    if prefs.get("favorite_genres"):
        genres = ", ".join(prefs["favorite_genres"])
        lines.append(
            f"- Favorite genres: {genres}. "
            "Suggest books from these genres unless the user asks for something else."
        )
    if not lines:
        return ""
    return "\n\n## User preferences\n" + "\n".join(lines)


def handle_preference_commands(user_input: str, prefs: Dict[str, Any]) -> bool:
    """
    Check if the user typed a preference command. Returns True if handled.

    Commands:
      /setcity <city>          — set default city
      /setgenre <genre,...>    — set favorite genres (comma-separated)
      /setname <name>          — set user name
      /prefs                   — show current preferences
      /clearprefs              — reset all preferences
    """
    lower = user_input.strip().lower()

    if lower.startswith("/setcity "):
        prefs["default_city"] = user_input.strip()[9:].strip()
        save_preferences(prefs)
        print(f"  Default city set to: {prefs['default_city']}")
        return True

    if lower.startswith("/setgenre "):
        genres = [g.strip() for g in user_input.strip()[10:].split(",") if g.strip()]
        prefs["favorite_genres"] = genres
        save_preferences(prefs)
        print(f"  Favorite genres set to: {genres}")
        return True

    if lower.startswith("/setname "):
        prefs["name"] = user_input.strip()[9:].strip()
        save_preferences(prefs)
        print(f"  Name set to: {prefs['name']}")
        return True

    if lower == "/prefs":
        print(f"  Current preferences: {json.dumps(prefs, indent=2)}")
        return True

    if lower == "/clearprefs":
        prefs.clear()
        prefs.update(DEFAULT_PREFS)
        save_preferences(prefs)
        print("  Preferences cleared.")
        return True

    return False


# ---------------------------------------------------------------------------
# ASCII banner — displayed once at startup
# ---------------------------------------------------------------------------
def print_banner():
    """Print a styled startup banner."""
    banner = f"""{C_MAGENTA}{C_BOLD}
  ┌─────────────────────────────────────────┐
  │                                         │
  │    *  W E E K E N D   W I Z A R D  *    │
  │        Your AI Weekend Planner          │
  │    Powered by Mistral 7B via Ollama     │
  │          Tools served via MCP           │
  │                                         │
  └─────────────────────────────────────────┘{C_RESET}
"""
    print(banner)


def print_help():
    """Print available commands and example prompts."""
    print(f"""
{C_BOLD}Commands:{C_RESET}
  {C_CYAN}/help{C_RESET}                — Show this help message
  {C_CYAN}/tools{C_RESET}               — List available MCP tools
  {C_CYAN}/clear{C_RESET}               — Clear conversation history
  {C_CYAN}/setcity <city>{C_RESET}      — Set default city for weather
  {C_CYAN}/setgenre <genres>{C_RESET}   — Set favorite genres (comma-separated)
  {C_CYAN}/setname <name>{C_RESET}      — Set your name for personalized greetings
  {C_CYAN}/prefs{C_RESET}               — Show current preferences
  {C_CYAN}/clearprefs{C_RESET}          — Reset all preferences
  {C_CYAN}/exit{C_RESET}                — Quit the agent

{C_BOLD}Example prompts:{C_RESET}
  Plan a cozy Saturday in NYC at (40.7128, -74.0060) with mystery books and a joke.
  What's the weather in Paris right now?
  Give me a trivia question and a dog pic.
  Suggest 3 sci-fi books and tell me a joke.

{C_DIM}Tip: The agent remembers context within a session. Ask follow-up questions!{C_RESET}
""")


# ---------------------------------------------------------------------------
# System prompt — teaches the model the ReAct cycle with strict one-at-a-time
# tool usage.  The explicit example is critical for small models like Mistral 7B.
# ---------------------------------------------------------------------------
SYSTEM = """\
You are Weekend Wizard, a cheerful and helpful weekend planning assistant.

## How you work (ReAct pattern)
You THINK about what you need, ACT by calling ONE tool, OBSERVE the result,
then THINK again. Repeat until you have everything, then give a final answer.

## Rules
1. Output ONLY valid JSON — no extra text before or after.
2. Call exactly ONE tool per turn. After you see the result you can call the next.
3. NEVER call the same tool twice with the same arguments — the data does not change.
4. When you have gathered enough information, finish with a final answer.
5. Your final answer MUST include the actual data from every tool you called (real numbers, real titles, real URLs). Never use placeholders.

## JSON formats

To call a tool (one at a time):
{"action": "<tool_name>", "args": {<arguments>}}

To give the final answer (answer MUST be a friendly text string with REAL data, NOT a template):
{"action": "final", "answer": "<WRITE YOUR ACTUAL ANSWER HERE using real data from tools>"}

## Available tools
- city_to_coords(city: str) — convert a city name to lat/long coordinates. Use FIRST if the user gives a city name instead of coordinates, then pass the result to get_weather.
- get_weather(latitude: float, longitude: float) — current weather at coordinates
- book_recs(topic: str, limit: int) — book recommendations for a topic
- random_joke() — a safe one-liner joke  (use empty args: {})
- random_dog() — random dog image URLs  (use empty args: {})
- trivia() — one multiple-choice trivia question (use empty args: {})

## Example turn sequence

User: "Plan a Saturday in NYC at (40.7128, -74.0060) with mystery books and a joke."

Turn 1 — you output:
{"action": "get_weather", "args": {"latitude": 40.7128, "longitude": -74.0060}}

(You then see the weather result as an observation.)

Turn 2 — you output:
{"action": "book_recs", "args": {"topic": "mystery", "limit": 3}}

(You see the book results.)

Turn 3 — you output:
{"action": "random_joke", "args": {}}

(You see the joke.)

Turn 4 — you now have everything, so you output:
{"action": "final", "answer": "Here is your cozy Saturday plan for NYC! The weather is currently 65F and partly cloudy — perfect for a stroll. I found two great mystery reads for you: 'The Big Sleep' by Raymond Chandler and 'Gone Girl' by Gillian Flynn. Here is a joke to brighten your day: Why did the scarecrow win an award? He was outstanding in his field! And here is a cute dog to cap it off: https://images.dog.ceo/breeds/retriever-golden/123.jpg. Enjoy your weekend!"}

Remember: ONE tool per turn. Wait for each result before calling the next tool.
"""


# ---------------------------------------------------------------------------
# JSON extraction — handles the many ways a small model can wrap JSON
# ---------------------------------------------------------------------------
def extract_json(text: str) -> Optional[Dict[str, Any]]:
    """
    Extract the first valid JSON object from LLM output.

    Handles:
    - Clean JSON
    - JSON inside ```json ... ``` or ``` ... ``` blocks
    - Multiple JSON objects on separate lines (takes first)
    - JSON preceded/followed by plain text
    """
    text = text.strip()

    # 1. Try direct parse (ideal case)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. Try extracting from markdown code blocks
    code_block = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if code_block:
        try:
            return json.loads(code_block.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 3. Try each line individually (handles multi-JSON output — take first)
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue

    # 4. Find first { ... } with regex
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group())
        except json.JSONDecodeError:
            pass

    return None


def llm_json(
    messages: List[Dict[str, str]],
    temperature: float = TOOL_TEMPERATURE,
    top_p: float = TOOL_TOP_P,
) -> Dict[str, Any]:
    """
    Call the local LLM and extract a JSON action from its response.
    Includes a repair step if initial parsing fails.

    Args:
        messages: Conversation history
        temperature: Controls randomness (0.0=deterministic, 1.0=creative)
        top_p: Nucleus sampling threshold (lower=more focused)
    """
    resp = chat(
        model=MODEL_NAME,
        messages=messages,
        options={"temperature": temperature, "top_p": top_p},
    )
    txt = resp["message"]["content"]

    parsed = extract_json(txt)
    if parsed is not None:
        return parsed

    # Repair step: ask the model to emit clean JSON (coldest settings)
    try:
        fix = chat(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "Return ONLY a single valid JSON object."},
                {"role": "user", "content": f"Convert this to valid JSON:\n{txt}"},
            ],
            options={"temperature": REPAIR_TEMPERATURE, "top_p": REPAIR_TOP_P},
        )
        parsed = extract_json(fix["message"]["content"])
        if parsed is not None:
            return parsed
    except Exception:
        pass

    # Last resort — surface the failure so the loop can handle it
    return {"action": "error", "message": f"Could not parse LLM output: {txt[:200]}"}


# ---------------------------------------------------------------------------
# Reflection — one-shot quality check before delivering the answer
# ---------------------------------------------------------------------------
def reflect_on_answer(question: str, answer: str, tool_history: List[Dict]) -> str:
    """
    Ask the LLM to review the proposed answer for completeness and accuracy.
    Returns the original answer if it passes, or a corrected version.
    """
    tools_summary = ", ".join(t["tool"] for t in tool_history) if tool_history else "none"

    # Build a concise summary of actual tool results for the checker
    tool_data_summary = ""
    for t in tool_history:
        tool_data_summary += f"\n- {t['tool']}: {t['result'][:300]}"

    reflection_prompt = (
        f"Review this answer for a user who asked: \"{question}\"\n\n"
        f"Tools called: {tools_summary}\n"
        f"Actual data received from tools:{tool_data_summary}\n\n"
        f"Proposed answer:\n{answer}\n\n"
        "Check:\n"
        "1. Does the answer include REAL data from the tool results (actual temperature, "
        "actual book titles, actual joke text, actual dog URL)? No placeholders!\n"
        "2. Is it friendly and upbeat?\n"
        "3. Did it address every part of the user's request?\n\n"
        "If the answer is complete and uses real data, reply EXACTLY: LOOKS_GOOD\n"
        "If there are issues, rewrite the answer using the actual tool data above."
    )

    try:
        resp = chat(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "You are a precise answer quality checker."},
                {"role": "user", "content": reflection_prompt},
            ],
            options={
                "temperature": REFLECTION_TEMPERATURE,
                "top_p": REFLECTION_TOP_P,
            },
        )
        reflection = resp["message"]["content"].strip()

        if "LOOKS_GOOD" in reflection.upper():
            print(f"  {C_CYAN}[reflection: answer approved]{C_RESET}")
            return answer
        else:
            print(f"  {C_CYAN}[reflection: answer corrected]{C_RESET}")
            return reflection

    except Exception:
        return answer  # fail-open: return original if reflection itself errors


# ---------------------------------------------------------------------------
# Post-processing — append real URLs if the model dropped them.
# Simple and minimal: don't mangle the model's prose, just guarantee
# that real links from tool results appear somewhere in the answer.
# ---------------------------------------------------------------------------
def post_process_answer(
    answer: str, user_input: str, tool_history: List[Dict]
) -> str:
    """Append missing tool URLs so real links always appear in the answer."""
    for t in tool_history:
        real_urls = re.findall(r'https?://[^\s"\',}]+', t["result"])
        if not real_urls:
            continue

        # Check if at least one real URL is already in the answer
        has_any = any(url in answer for url in real_urls)
        if has_any:
            continue

        # URLs are missing — append them
        links = "\n".join(f"  - {url}" for url in real_urls)
        answer += f"\n{links}"

    return answer


# ---------------------------------------------------------------------------
# Main agent loop
# ---------------------------------------------------------------------------
MAX_TOOL_ITERATIONS = 8  # enough for 5 tools + retries


async def main():
    """Connect to MCP server, run interactive ReAct loop."""

    server_path = sys.argv[1] if len(sys.argv) > 1 else "server_fun.py"

    # --- MCP connection setup ---
    exit_stack = AsyncExitStack()
    stdio = await exit_stack.enter_async_context(
        stdio_client(StdioServerParameters(command="python", args=[server_path]))
    )
    r_in, w_out = stdio
    session = await exit_stack.enter_async_context(ClientSession(r_in, w_out))
    await session.initialize()

    tools = (await session.list_tools()).tools
    tool_index = {t.name: t for t in tools}

    # --- Load user preferences ---
    prefs = load_preferences()
    prefs_section = prefs_to_prompt_section(prefs)
    system_prompt = SYSTEM + prefs_section

    print_banner()
    print(f"{C_GREEN}Connected tools:{C_RESET} {list(tool_index.keys())}")
    if any(prefs.get(k) for k in ("name", "default_city", "favorite_genres")):
        print(f"{C_CYAN}Loaded preferences:{C_RESET} {json.dumps({k: v for k, v in prefs.items() if v}, indent=2)}")
    print(f"\n{C_DIM}Type /help for commands, /exit or Ctrl+C to quit.{C_RESET}")
    print(f"{C_DIM}The agent remembers context within this session.{C_RESET}\n")

    history: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]

    try:
        while True:
            try:
                user_input = input("You: ").strip()
            except (KeyboardInterrupt, EOFError):
                print()  # newline after ^C
                break
            if not user_input or user_input.lower() in {"exit", "quit"}:
                break

            # Handle slash commands
            if user_input.startswith("/"):
                cmd = user_input.strip().lower()
                if cmd in {"/exit", "/quit"}:
                    break
                if cmd == "/help":
                    print_help()
                    continue
                if cmd == "/tools":
                    print(f"\n{C_BOLD}Available MCP Tools:{C_RESET}")
                    for name, tool in tool_index.items():
                        desc = tool.description or "No description"
                        # Truncate long descriptions to first sentence
                        first_sentence = desc.split(".")[0] + "."
                        print(f"  {C_CYAN}{name}{C_RESET} — {first_sentence}")
                    print()
                    continue
                if cmd == "/clear":
                    history.clear()
                    history.append({"role": "system", "content": system_prompt})
                    print(f"  {C_CYAN}Conversation cleared. Starting fresh!{C_RESET}")
                    continue
                if handle_preference_commands(user_input, prefs):
                    # Rebuild system prompt with updated preferences
                    prefs_section = prefs_to_prompt_section(prefs)
                    system_prompt = SYSTEM + prefs_section
                    history[0] = {"role": "system", "content": system_prompt}
                    continue
                else:
                    print(f"  {C_RED}Unknown command: {user_input}{C_RESET}")
                    print(f"  {C_DIM}Type /help for available commands.{C_RESET}")
                    continue

            history.append({"role": "user", "content": user_input})
            tool_history: List[Dict] = []

            # --- ReAct loop ---
            answered = False
            for iteration in range(MAX_TOOL_ITERATIONS):
                decision = llm_json(history)
                action = decision.get("action", "")

                # ---- Final answer ----
                if action == "final":
                    answer = decision.get("answer", "I couldn't come up with an answer.")

                    # If the model returned JSON instead of prose, convert
                    # it to a readable string in code (no LLM retry needed)
                    if not isinstance(answer, str):
                        answer = json.dumps(answer, indent=2)
                    if isinstance(answer, str) and answer.strip().startswith("{"):
                        try:
                            data = json.loads(answer)
                            # Pull out any "message" field the model included
                            parts = []
                            if isinstance(data, dict):
                                msg = data.get("message", "")
                                if msg:
                                    parts.append(msg)
                                # Flatten remaining values into readable text
                                for k, v in data.items():
                                    if k == "message":
                                        continue
                                    if isinstance(v, str) and v:
                                        parts.append(f"{k.replace('_', ' ').title()}: {v}")
                            if parts:
                                answer = " ".join(parts)
                            # else leave as-is, post_process will add URLs
                        except json.JSONDecodeError:
                            pass  # not valid JSON, leave as-is

                    # Reflection pass
                    answer = reflect_on_answer(user_input, answer, tool_history)
                    # Ensure real URLs from tool results appear in the answer
                    answer = post_process_answer(answer, user_input, tool_history)

                    print(f"\n{C_GREEN}{C_BOLD}Agent:{C_RESET} {C_GREEN}{answer}{C_RESET}\n")
                    history.append({"role": "assistant", "content": answer})
                    answered = True
                    break

                # ---- Parse / LLM error ----
                if action == "error":
                    msg = decision.get("message", "unknown error")
                    print(f"  {C_RED}[error: {msg}]{C_RESET}")
                    # Give the model one more chance with a nudge
                    history.append({
                        "role": "user",
                        "content": (
                            "[System] Your last output was not valid JSON. "
                            "Remember: output ONLY a single JSON object. "
                            "Either call a tool or give a final answer."
                        ),
                    })
                    continue

                # ---- Tool call ----
                tname = action
                args = decision.get("args", {})

                if tname not in tool_index:
                    # Unknown tool — tell the model and let it retry
                    history.append({
                        "role": "user",
                        "content": (
                            f"[Observation] Unknown tool '{tname}'. "
                            f"Available tools: {list(tool_index.keys())}"
                        ),
                    })
                    continue

                # Duplicate-call detection: skip if same tool+args already called
                call_key = f"{tname}:{json.dumps(args, sort_keys=True)}"
                already_called = any(
                    f"{t['tool']}:{json.dumps(t['args'], sort_keys=True)}" == call_key
                    for t in tool_history
                )
                if already_called:
                    print(f"  {C_DIM}[skipping duplicate call: {tname}({args})]{C_RESET}")
                    history.append({
                        "role": "user",
                        "content": (
                            f"[Observation] You already called {tname} with these "
                            f"arguments — see the earlier result. Call a DIFFERENT tool "
                            f"or give your final answer."
                        ),
                    })
                    continue

                print(f"  {C_YELLOW}[calling tool: {tname}({args})]...{C_RESET}")
                t_start = time.time()

                try:
                    result = await session.call_tool(tname, args)
                    payload = (
                        result.content[0].text
                        if result.content
                        else json.dumps({"result": "empty"})
                    )
                except Exception as e:
                    payload = json.dumps({"error": str(e)})

                elapsed = time.time() - t_start
                print(f"  {C_YELLOW}[tool {tname} returned in {elapsed:.1f}s]{C_RESET}")
                tool_history.append({"tool": tname, "args": args, "result": payload})

                # Build a summary of what tools have been called so far
                tools_done = [t["tool"] for t in tool_history]
                tools_remaining = [
                    t for t in tool_index.keys() if t not in tools_done
                ]

                # Inject the observation as a 'user' message so the model sees
                # it as new information rather than something it already said.
                # Include a progress summary to keep the model on track.
                history.append({
                    "role": "user",
                    "content": (
                        f"[Observation from {tname}]: {payload}\n\n"
                        f"Tools called so far: {tools_done}. "
                        f"Remaining tools available: {tools_remaining}. "
                        f"Call the next tool you need, or give your final answer."
                    ),
                })

            # If the loop exhausted without a final answer, force one
            if not answered:
                print(f"  {C_YELLOW}[loop limit reached — forcing final answer]{C_RESET}")
                history.append({
                    "role": "user",
                    "content": (
                        "[System] You have called enough tools. Now provide your "
                        "final answer using the data you have gathered. Output JSON: "
                        '{"action": "final", "answer": "..."}'
                    ),
                })
                decision = llm_json(
                    history,
                    temperature=ANSWER_TEMPERATURE,
                    top_p=ANSWER_TOP_P,
                )
                answer = decision.get("answer", decision.get("message", "Sorry, I ran out of steps!"))
                answer = reflect_on_answer(user_input, answer, tool_history)
                answer = post_process_answer(answer, user_input, tool_history)
                print(f"\n{C_GREEN}{C_BOLD}Agent:{C_RESET} {C_GREEN}{answer}{C_RESET}\n")
                history.append({"role": "assistant", "content": answer})

    finally:
        await exit_stack.aclose()
        print(f"\n{C_MAGENTA}Goodbye from Weekend Wizard!{C_RESET}")


if __name__ == "__main__":
    asyncio.run(main())

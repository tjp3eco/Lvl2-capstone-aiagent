"""
MCP Server for Weekend Wizard Agent
Exposes fun tools via Model Context Protocol
Uses free, no-key-required APIs
"""

from mcp.server.fastmcp import FastMCP
from typing import Optional, Dict, Any, List
import requests
import html
import time
import random
import os

# ---------------------------------------------------------------------------
# SSL verification is disabled because common deployment environments
# (corporate proxies, educational networks) re-sign TLS certificates,
# causing validation failures with Python's bundled CA store.
# All APIs used are public, free, and return non-sensitive data.
# To enable strict verification: set environment variable VERIFY_SSL=true
# ---------------------------------------------------------------------------
VERIFY_SSL = os.environ.get("VERIFY_SSL", "false").lower() in ("1", "true", "yes")


# Initialize MCP server
mcp = FastMCP("FunTools")


# ---------------------------------------------------------------------------
# Stretch Goal: Retry with exponential backoff
# ---------------------------------------------------------------------------
def _request_with_retry(
    url: str,
    params: Optional[Dict] = None,
    max_retries: int = 3,
    base_delay: float = 1.0,
    timeout: int = 20,
) -> requests.Response:
    """
    GET request with exponential backoff retry logic.

    Retries on transient failures (timeouts, 429 rate limits, 5xx server errors).
    Raises the last exception if all retries are exhausted.

    Args:
        url: The URL to request
        params: Query parameters
        max_retries: Maximum number of retry attempts (default 3)
        base_delay: Starting delay in seconds, doubles each retry (1 -> 2 -> 4)
        timeout: Request timeout in seconds
    """
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            r = requests.get(url, params=params, timeout=timeout, verify=VERIFY_SSL)

            # Retry on rate limit (429) or server errors (5xx)
            if r.status_code == 429 or r.status_code >= 500:
                if attempt < max_retries:
                    delay = base_delay * (2 ** attempt)
                    time.sleep(delay)
                    continue
            r.raise_for_status()
            return r

        except requests.exceptions.Timeout as e:
            last_error = e
            if attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                time.sleep(delay)
                continue

        except requests.exceptions.ConnectionError as e:
            last_error = e
            if attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                time.sleep(delay)
                continue

        except requests.exceptions.HTTPError:
            raise  # Non-retryable HTTP errors (4xx except 429)

    raise last_error  # All retries exhausted


# ---- Weather (Open-Meteo) ----
@mcp.tool()
def get_weather(latitude: float, longitude: float) -> Dict[str, Any]:
    """
    Get current weather conditions at the specified coordinates.

    Args:
        latitude: The latitude coordinate (e.g., 40.7128 for NYC)
        longitude: The longitude coordinate (e.g., -74.0060 for NYC)

    Returns:
        Dictionary with temperature (C), weather code, and wind speed
    """
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,weather_code,wind_speed_10m",
        "timezone": "auto",
    }

    try:
        r = _request_with_retry(url, params=params)
        current = r.json().get("current", {})

        # Map weather code to condition string
        weather_codes = {
            0: "clear sky",
            1: "mainly clear",
            2: "partly cloudy",
            3: "overcast",
            45: "foggy",
            48: "depositing rime fog",
            51: "light drizzle",
            53: "moderate drizzle",
            55: "dense drizzle",
            61: "light rain",
            63: "moderate rain",
            65: "heavy rain",
            71: "light snow",
            73: "moderate snow",
            75: "heavy snow",
            95: "thunderstorm",
        }

        code = current.get("weather_code", 0)
        condition = weather_codes.get(code, "unknown")

        return {
            "temperature_c": current.get("temperature_2m"),
            "temperature_f": round(current.get("temperature_2m", 0) * 9/5 + 32, 1),
            "weather_code": code,
            "condition": condition,
            "wind_speed_kmh": current.get("wind_speed_10m"),
        }
    except Exception as e:
        return {"error": f"Failed to fetch weather: {str(e)}"}


# ---- Book Recommendations (Open Library) ----
@mcp.tool()
def book_recs(topic: str, limit: int = 5) -> Dict[str, Any]:
    """
    Get book recommendations for a topic from Open Library.

    Args:
        topic: The topic or genre (e.g., "mystery", "science fiction", "history")
        limit: Number of recommendations (default 5, max 10)

    Returns:
        Dictionary with topic and list of book results
    """
    try:
        limit = min(limit, 10)  # Cap at 10

        r = _request_with_retry(
            "https://openlibrary.org/search.json",
            params={"q": topic, "limit": limit, "sort": "rating desc"},
        )
        docs = r.json().get("docs", [])

        picks = []
        for d in docs[:limit]:
            picks.append({
                "title": d.get("title", "Unknown"),
                "author": (d.get("author_name") or ["Unknown"])[0],
                "year": d.get("first_publish_year"),
                "rating": d.get("ratings_average"),
                "work_key": d.get("key"),
            })

        return {
            "topic": topic,
            "results": picks,
            "total_found": r.json().get("numFound", 0)
        }
    except Exception as e:
        return {"error": f"Failed to fetch book recommendations: {str(e)}"}


# ---- Random Joke (JokeAPI) ----
@mcp.tool()
def random_joke() -> Dict[str, Any]:
    """
    Get a safe, single-line joke.

    Returns:
        Dictionary with the joke text
    """
    try:
        r = _request_with_retry(
            "https://v2.jokeapi.dev/joke/Any",
            params={"type": "single", "safe-mode": True},
        )
        data = r.json()

        if data.get("type") == "single":
            return {"joke": data.get("joke", "No joke found")}
        else:
            # Handle two-part jokes
            setup = data.get("setup", "")
            delivery = data.get("delivery", "")
            return {"joke": f"{setup} {delivery}"}
    except Exception as e:
        # Fallback jokes
        fallbacks = [
            "Why don't scientists trust atoms? Because they make up everything!",
            "I told my computer I needed a break, and now it won't stop sending me Kit-Kats.",
            "Why did the scarecrow win an award? He was outstanding in his field!"
        ]
        return {"joke": random.choice(fallbacks), "note": "Fallback joke used"}


# ---- Random Dog Photo (Dog CEO) ----
@mcp.tool()
def random_dog(count: int = 3) -> Dict[str, Any]:
    """
    Get random dog image URLs.

    Args:
        count: Number of dog images to return (default 3, max 5)

    Returns:
        Dictionary with image URLs and breed information
    """
    try:
        count = max(1, min(count, 5))  # Clamp between 1 and 5

        if count == 1:
            r = _request_with_retry("https://dog.ceo/api/breeds/image/random")
            data = r.json()
            urls = [data.get("message", "")]
        else:
            r = _request_with_retry(f"https://dog.ceo/api/breeds/image/random/{count}")
            data = r.json()
            urls = data.get("message", [])

        # Extract breed from each URL
        dogs = []
        for url in urls:
            breed = "unknown"
            if "/breeds/" in url:
                try:
                    breed_part = url.split("/breeds/")[1].split("/")[0]
                    breed = breed_part.replace("-", " ").title()
                except Exception:
                    pass
            dogs.append({"image_url": url, "breed": breed})

        return {
            "count": len(dogs),
            "dogs": dogs,
            "status": data.get("status", "unknown")
        }
    except Exception as e:
        return {
            "error": f"Failed to fetch dog image: {str(e)}",
            "fallback_url": "https://images.dog.ceo/breeds/retriever-golden/n02099601_3004.jpg"
        }


# ---- Optional: Trivia Question ----
@mcp.tool()
def trivia() -> Dict[str, Any]:
    """
    Get one trivia question.

    Returns:
        Dictionary with question, options, and correct answer
    """
    try:
        r = _request_with_retry(
            "https://opentdb.com/api.php",
            params={"amount": 1, "type": "multiple"},
        )
        data = r.json()
        results = data.get("results", [])

        if not results:
            return {"error": "No trivia question available"}

        q = results[0]

        # Unescape HTML entities
        question = html.unescape(q.get("question", ""))
        correct = html.unescape(q.get("correct_answer", ""))
        incorrect = [html.unescape(x) for x in q.get("incorrect_answers", [])]

        # Combine and shuffle options
        all_options = incorrect + [correct]
        random.shuffle(all_options)

        return {
            "category": html.unescape(q.get("category", "")),
            "difficulty": q.get("difficulty", ""),
            "question": question,
            "options": all_options,
            "correct_answer": correct,
            "hint": f"The answer has {len(correct)} characters"
        }
    except Exception as e:
        # Fallback trivia
        return {
            "category": "Science: Computers",
            "difficulty": "medium",
            "question": "What does 'CPU' stand for?",
            "options": ["Central Process Unit", "Computer Personal Unit", "Central Processing Unit", "Central Processor Unit"],
            "correct_answer": "Central Processing Unit",
            "note": "Fallback question due to API error"
        }


# ---- Stretch Goal: City-to-Coordinates Geocoding (Open-Meteo) ----
@mcp.tool()
def city_to_coords(city: str) -> Dict[str, Any]:
    """
    Convert a city name to latitude/longitude coordinates.

    Use this tool when the user mentions a city name instead of coordinates.
    Pass the returned latitude and longitude to get_weather().

    Args:
        city: The city name (e.g., "Paris", "New York", "Tokyo")

    Returns:
        Dictionary with latitude, longitude, country, and timezone
    """
    try:
        r = _request_with_retry(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1, "language": "en", "format": "json"},
        )
        results = r.json().get("results", [])

        if not results:
            return {"error": f"Could not find coordinates for '{city}'"}

        loc = results[0]
        return {
            "city": loc.get("name"),
            "latitude": loc.get("latitude"),
            "longitude": loc.get("longitude"),
            "country": loc.get("country", "Unknown"),
            "timezone": loc.get("timezone", "Unknown"),
            "population": loc.get("population"),
        }
    except Exception as e:
        return {"error": f"Failed to geocode '{city}': {str(e)}"}


# Run the server
if __name__ == "__main__":
    mcp.run()  # stdio server

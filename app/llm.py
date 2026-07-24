"""
app/llm.py — ONE place that talks to a language model.

The rest of the app never cares which provider is active. It just calls:

    from app.llm import ask
    reply = ask("Explain attention in one sentence.")

Which provider actually runs is decided by the LLM_PROVIDER env var:
    groq    -> Groq cloud (OpenAI-compatible API)   [default]
    gemini  -> Google Gemini REST API
    ollama  -> a model running locally via Ollama

We deliberately use plain `requests` (no vendor SDKs) so there are fewer
dependencies and version conflicts, and the three code paths look similar.
"""

from __future__ import annotations

import json

import requests

from app.config import settings

# A generous timeout: enrichment prompts can take a while on big models.
_TIMEOUT = 120


class LLMError(RuntimeError):
    """Raised when the model call fails or a needed API key is missing."""


def ask(
    prompt: str,
    system: str | None = None,
    json_mode: bool = False,
    temperature: float = 0.4,
) -> str:
    """
    Send `prompt` to the configured LLM and return its text reply.

    Args:
        prompt:      The user message.
        system:      Optional system instruction that sets the model's role.
        json_mode:   If True, ask the provider to return strict JSON. (We still
                     parse defensively at the call site.)
        temperature: Higher = more creative, lower = more deterministic.

    Returns:
        The model's reply as a string.

    Raises:
        LLMError: on misconfiguration or a failed API call.
    """
    provider = settings.LLM_PROVIDER

    if provider == "groq":
        return _ask_groq(prompt, system, json_mode, temperature)
    if provider == "gemini":
        return _ask_gemini(prompt, system, json_mode, temperature)
    if provider == "ollama":
        return _ask_ollama(prompt, system, json_mode, temperature)

    raise LLMError(
        f"Unknown LLM_PROVIDER '{provider}'. Use one of: groq, gemini, ollama."
    )


# ---------------------------------------------------------------------------
# Groq  (OpenAI-compatible Chat Completions API)
# ---------------------------------------------------------------------------
def _ask_groq(prompt, system, json_mode, temperature) -> str:
    if not settings.GROQ_API_KEY:
        raise LLMError(
            "GROQ_API_KEY is not set. Get a free key at https://console.groq.com/keys "
            "and add it to your .env file."
        )

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    body: dict = {
        "model": settings.GROQ_MODEL,
        "messages": messages,
        "temperature": temperature,
    }
    if json_mode:
        # Groq supports OpenAI's JSON mode: the model must return valid JSON.
        body["response_format"] = {"type": "json_object"}

    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {settings.GROQ_API_KEY}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=_TIMEOUT,
    )
    _raise_for_status(resp, "Groq")
    data = resp.json()
    return data["choices"][0]["message"]["content"]


# ---------------------------------------------------------------------------
# Google Gemini  (generateContent REST API)
# ---------------------------------------------------------------------------
def _ask_gemini(prompt, system, json_mode, temperature) -> str:
    if not settings.GEMINI_API_KEY:
        raise LLMError(
            "GEMINI_API_KEY is not set. Get a free key at "
            "https://aistudio.google.com/apikey and add it to your .env file."
        )

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.GEMINI_MODEL}:generateContent?key={settings.GEMINI_API_KEY}"
    )

    generation_config: dict = {"temperature": temperature}
    if json_mode:
        generation_config["responseMimeType"] = "application/json"

    body: dict = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": generation_config,
    }
    # Gemini takes the system prompt in its own field.
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}

    resp = requests.post(url, json=body, timeout=_TIMEOUT)
    _raise_for_status(resp, "Gemini")
    data = resp.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        raise LLMError(f"Unexpected Gemini response shape: {data}") from exc


# ---------------------------------------------------------------------------
# Ollama  (local models; no API key)
# ---------------------------------------------------------------------------
def _ask_ollama(prompt, system, json_mode, temperature) -> str:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    body: dict = {
        "model": settings.OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature},
    }
    if json_mode:
        # Ollama accepts "format": "json" to force JSON output.
        body["format"] = "json"

    try:
        resp = requests.post(
            f"{settings.OLLAMA_HOST}/api/chat",
            json=body,
            timeout=_TIMEOUT,
        )
    except requests.ConnectionError as exc:
        raise LLMError(
            f"Could not reach Ollama at {settings.OLLAMA_HOST}. Is `ollama serve` "
            f"running and the model pulled (`ollama pull {settings.OLLAMA_MODEL}`)?"
        ) from exc

    _raise_for_status(resp, "Ollama")
    data = resp.json()
    return data["message"]["content"]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
def _raise_for_status(resp: requests.Response, provider: str) -> None:
    """Turn HTTP errors into a clear LLMError with the provider's message."""
    if resp.status_code >= 400:
        # Try to surface the provider's own error message for easier debugging.
        try:
            detail = json.dumps(resp.json())
        except Exception:
            detail = resp.text
        raise LLMError(f"{provider} API error {resp.status_code}: {detail}")

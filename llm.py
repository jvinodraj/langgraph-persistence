"""
llm.py - one place that knows how to build a chat model.

Nothing in this repo calls a model. That is deliberate: persistence is about where state is stored, not about what
a node computes, so every example here is deterministic and runs instantly with no API key.

The file is kept so that Session 3 (human-in-the-loop) and anyone who wants to swap a node for a real model have the
wiring already done. The three-line change is documented under "Where the model goes" in the README.

We talk to OpenRouter (an OpenAI-compatible gateway) through LangChain's ChatOpenAI class, so switching from GPT to
Claude to Gemini to Llama is just a different model-name string - nothing else in the app changes.
"""
import os

from dotenv import load_dotenv

try:  # importing this module must still work if langchain-openai is not installed
    from langchain_openai import ChatOpenAI
except ImportError:  # pragma: no cover
    ChatOpenAI = None

load_dotenv()  # reads OPENROUTER_API_KEY from a local .env file (ignored by git)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "openai/gpt-4o-mini"


def has_api_key() -> bool:
    """True when OPENROUTER_API_KEY is available."""
    return bool(os.getenv("OPENROUTER_API_KEY"))


def get_llm(temperature: float = 0.3):
    """Return a ChatOpenAI pointed at OpenRouter, always using DEFAULT_MODEL."""
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY is not set (see .env.example).")
    if ChatOpenAI is None:  # pragma: no cover
        raise ImportError("langchain-openai is not installed. Run: python -m pip install -r requirements.txt")
    return ChatOpenAI(
        model=DEFAULT_MODEL,
        api_key=api_key,
        base_url=OPENROUTER_BASE_URL,
        temperature=temperature,
    )

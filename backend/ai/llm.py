"""Creates the chat model. Gemini (default) or a local Ollama model. Never fakes an answer."""
from backend.config import env


class LLMUnavailable(RuntimeError):
    """Raised when no usable LLM is configured."""


def get_llm():
    provider = env("LLM_PROVIDER", "gemini").lower()
    if provider == "ollama":
        try:
            from langchain_ollama import ChatOllama
        except ImportError as e:
            raise LLMUnavailable("langchain-ollama is not installed.") from e
        return ChatOllama(model=env("OLLAMA_MODEL", "llama3.1"), base_url=env("OLLAMA_URL", "http://localhost:11434"), temperature=0.3)
    key = env("GEMINI_API_KEY")
    if not key:
        raise LLMUnavailable("GEMINI_API_KEY is not set. Add it to the .env file (free key: https://aistudio.google.com/apikey) "
                             "or set LLM_PROVIDER=ollama to use a local model.")
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
    except ImportError as e:
        raise LLMUnavailable("langchain-google-genai is not installed.") from e
    return ChatGoogleGenerativeAI(model=env("GEMINI_MODEL", "gemini-3.8-flash"), google_api_key=key, temperature=0.3, max_retries=1, timeout=45)


def text_of(message) -> str:
    """Normalise a model reply to plain text (some models return a list of parts)."""
    c = getattr(message, "content", message)
    if isinstance(c, list):
        return "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in c).strip()
    return str(c).strip()


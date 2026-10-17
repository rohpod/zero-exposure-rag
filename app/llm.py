"""
Wrapper around the Granite model, served in-process via llama-cpp-python.

The model is loaded once at import time (module-level singleton) so
individual requests do not pay the load cost.
"""
from pathlib import Path

from llama_cpp import Llama

MODEL_PATH = Path(__file__).parent.parent / "models" / "granite-4.0-h-350m-base-be.f16.gguf"

_llm: Llama | None = None


def _get_llm() -> Llama:
    global _llm
    if _llm is None:
        if not MODEL_PATH.exists():
            raise FileNotFoundError(
                f"Model not found at {MODEL_PATH}. See docs/environment.md "
                "for how to obtain it."
            )
        _llm = Llama(model_path=str(MODEL_PATH), n_ctx=2048, verbose=False)
    return _llm


def generate(prompt: str, max_tokens: int = 256, temperature: float = 0.0) -> str:
    """
    Generate a completion for the given prompt.
    """
    llm = _get_llm()
    out = llm(prompt, max_tokens=max_tokens, temperature=temperature)
    return out["choices"][0]["text"]

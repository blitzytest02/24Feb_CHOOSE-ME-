"""
app/utils/token_counter.py — GPT-2 Tokenizer-Based Token Counting

Provides token counting functionality for context window management using the
GPT-2 tokenizer from the HuggingFace ``transformers`` library.  The GPT-2
tokenizer serves as a universal approximate counter that yields consistent
token estimates across different LLM providers (Anthropic Claude, OpenAI GPT,
Voyage AI) — good enough for managing context-window budgets without requiring
provider-specific tokenizers.

Key design decisions:
  • Lazy singleton — the tokenizer is loaded on first use (not at import
    time) to avoid slow module-level I/O when the utility is imported but
    never called.
  • Graceful fallback — if the ``transformers`` library is missing or the
    pretrained model cannot be loaded, all public functions silently degrade
    to a word-based approximation (≈ 1.3 tokens per whitespace-delimited
    word) and emit a WARNING-level log message.
  • Stateless public API — every function is a pure mapping from its
    arguments to its return value; the only shared mutable state is the
    ``_tokenizer`` singleton, which is set once and never mutated again.

Exports:
  count_tokens            — count the number of tokens in a text string
  count_tokens_for_messages — sum token counts across a list of LLM messages
  fits_in_context         — check whether a text fits within a token budget
  truncate_to_token_limit — trim text to a maximum number of tokens
  CONTEXT_400K            — 400 000 tokens (Claude Opus 4.6 context window)
  DEFAULT_MAX_TOKENS      — 200 000 tokens (default operational limit)
  TOKENIZER_NAME          — "gpt2" (HuggingFace model identifier)
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional, Union

# ---------------------------------------------------------------------------
# Module-level logger
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

CONTEXT_400K: int = 400_000
"""Maximum context window size in tokens.  Matches the extended context
window of Anthropic Claude Opus 4.6 (400 K tokens)."""

DEFAULT_MAX_TOKENS: int = 200_000
"""Default maximum token limit used when no explicit budget is provided."""

TOKENIZER_NAME: str = "gpt2"
"""HuggingFace model identifier for the GPT-2 tokenizer."""

# ---------------------------------------------------------------------------
# Approximate word → token ratio used as a fallback when the real tokenizer
# is unavailable.  GPT-class models average ~1.3 tokens per English word.
# ---------------------------------------------------------------------------
_WORD_TOKEN_RATIO: float = 1.3

# ---------------------------------------------------------------------------
# Overhead tokens per message for role/formatting metadata when counting
# tokens across a message list (role name, delimiters, etc.).
# ---------------------------------------------------------------------------
_MESSAGE_OVERHEAD_TOKENS: int = 4

# ---------------------------------------------------------------------------
# Lazy-loaded tokenizer singleton
# ---------------------------------------------------------------------------
_tokenizer: Optional[Any] = None
_tokenizer_loaded: bool = False  # distinguishes "not yet tried" from "tried and failed"


def _get_tokenizer() -> Optional[Any]:
    """Return the lazily-initialised GPT-2 tokenizer singleton.

    On the first call the function attempts to load
    ``GPT2TokenizerFast.from_pretrained("gpt2")``.  If that class is not
    available it falls back to ``GPT2Tokenizer``.  If **both** fail (e.g.
    the ``transformers`` package is not installed or the model cache is
    inaccessible), the function logs a WARNING and returns ``None`` — all
    downstream public functions will then use the approximate word-based
    counting fallback.

    Returns:
        A ``GPT2TokenizerFast`` (preferred) or ``GPT2Tokenizer`` instance,
        or ``None`` when the tokenizer cannot be loaded.
    """
    global _tokenizer, _tokenizer_loaded

    if _tokenizer_loaded:
        # Already attempted initialisation — return whatever we got (may be None).
        return _tokenizer

    _tokenizer_loaded = True

    # --- Attempt 1: GPT2TokenizerFast (preferred — Rust-backed, ~3× faster) ---
    try:
        from transformers import GPT2TokenizerFast  # noqa: WPS433

        _tokenizer = GPT2TokenizerFast.from_pretrained(TOKENIZER_NAME)
        logger.info(
            "GPT-2 tokenizer (fast) initialised successfully "
            "(vocab_size=%d, model=%s)",
            _tokenizer.vocab_size,
            TOKENIZER_NAME,
        )
        return _tokenizer
    except Exception:  # noqa: BLE001
        logger.debug(
            "GPT2TokenizerFast not available; attempting GPT2Tokenizer fallback.",
            exc_info=True,
        )

    # --- Attempt 2: GPT2Tokenizer (pure-Python fallback) ---
    try:
        from transformers import GPT2Tokenizer  # noqa: WPS433

        _tokenizer = GPT2Tokenizer.from_pretrained(TOKENIZER_NAME)
        logger.info(
            "GPT-2 tokenizer (standard) initialised successfully "
            "(vocab_size=%d, model=%s)",
            _tokenizer.vocab_size,
            TOKENIZER_NAME,
        )
        return _tokenizer
    except Exception:  # noqa: BLE001
        logger.debug(
            "GPT2Tokenizer also not available.",
            exc_info=True,
        )

    # --- All attempts exhausted ---
    logger.warning(
        "Could not load GPT-2 tokenizer from the 'transformers' library. "
        "Token counting will fall back to approximate word-based estimation "
        "(ratio=%.1f tokens/word).  Install 'transformers' and ensure the "
        "'gpt2' model is accessible to restore precise counting.",
        _WORD_TOKEN_RATIO,
    )
    return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _approximate_token_count(text: str) -> int:
    """Estimate token count from whitespace-delimited word count.

    This is only used when the GPT-2 tokenizer is unavailable.  The
    approximation uses a ratio of ~1.3 tokens per word, which is a
    reasonable average for English prose processed by GPT-class BPE
    tokenizers.

    Args:
        text: The input string.

    Returns:
        Estimated number of tokens (always >= 0).
    """
    if not text:
        return 0
    word_count = len(text.split())
    return max(1, math.ceil(word_count * _WORD_TOKEN_RATIO))


def _extract_message_content(message: Union[Dict[str, Any], Any]) -> str:
    """Extract the textual content from a single LLM/LangChain message.

    Supports:
      • Plain ``dict`` objects with a ``"content"`` key.
      • LangChain ``BaseMessage`` subclasses that expose a ``.content``
        attribute.
      • Plain strings (returned as-is).

    Args:
        message: A single message in any of the supported formats.

    Returns:
        The extracted text content, or an empty string when the message
        format is unrecognised.
    """
    if isinstance(message, str):
        return message

    # dict-style message — e.g. {"role": "user", "content": "..."}
    if isinstance(message, dict):
        content = message.get("content", "")
        return str(content) if content is not None else ""

    # Object-style message (LangChain BaseMessage or similar)
    content = getattr(message, "content", None)
    if content is not None:
        return str(content)

    # Last resort — stringify the entire message
    return str(message)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def count_tokens(text: str) -> int:
    """Count the number of tokens in *text* using the GPT-2 tokenizer.

    If the tokenizer is unavailable (e.g. ``transformers`` is not installed),
    the function silently falls back to an approximate word-based count
    (≈ 1.3 tokens per word) and logs a warning on the first fallback
    invocation.

    Args:
        text: The text content to tokenise and count.

    Returns:
        The number of tokens (always >= 0).  Returns ``0`` for ``None``
        or empty strings.
    """
    if not text:
        return 0

    tokenizer = _get_tokenizer()

    if tokenizer is not None:
        try:
            tokens = tokenizer.encode(text)
            return len(tokens)
        except Exception:  # noqa: BLE001
            logger.warning(
                "GPT-2 tokenizer encode() failed; falling back to "
                "approximate word-based counting.",
                exc_info=True,
            )

    # Fallback: approximate counting
    return _approximate_token_count(text)


def count_tokens_for_messages(messages: List[Union[Dict[str, Any], Any]]) -> int:
    """Count the total token budget consumed by a list of LLM messages.

    Each message incurs:
      • The tokens of its textual ``content``.
      • A fixed overhead of ~4 tokens for role metadata and delimiters
        (matching the overhead convention used by OpenAI chat completions).

    Supports both ``dict``-style messages (``{"role": "...", "content":
    "..."}``) and LangChain ``BaseMessage`` instances that expose a
    ``.content`` attribute.

    Args:
        messages: An iterable of message objects or dicts.

    Returns:
        Estimated total token count across all messages (always >= 0).
        Returns ``0`` for ``None`` or empty lists.
    """
    if not messages:
        return 0

    total_tokens: int = 0

    for message in messages:
        content = _extract_message_content(message)
        total_tokens += count_tokens(content)
        total_tokens += _MESSAGE_OVERHEAD_TOKENS

    return total_tokens


def fits_in_context(text: str, max_tokens: int = CONTEXT_400K) -> bool:
    """Check whether *text* fits within the given token budget.

    This is a convenience wrapper around :func:`count_tokens` that returns
    a boolean instead of a token count — useful for guard-clauses before
    sending content to LLM APIs.

    Args:
        text: The text content to check.
        max_tokens: The maximum allowed number of tokens.  Defaults to
            :data:`CONTEXT_400K` (400 000).

    Returns:
        ``True`` if ``count_tokens(text) <= max_tokens``, ``False``
        otherwise.  Returns ``True`` for ``None`` or empty strings
        (0 tokens always fits).
    """
    if not text:
        return True
    return count_tokens(text) <= max_tokens


def truncate_to_token_limit(
    text: str,
    max_tokens: int,
    preserve_end: bool = False,
) -> str:
    """Truncate *text* so that it contains at most *max_tokens* tokens.

    The truncation is performed precisely via the GPT-2 tokenizer's
    ``encode()`` / ``decode()`` round-trip.  When the tokenizer is
    unavailable, a word-level approximation is used instead.

    Args:
        text: The input text to (potentially) truncate.
        max_tokens: The maximum number of tokens allowed in the output.
        preserve_end: When ``True`` the *end* of the text is preserved
            (the beginning is trimmed).  When ``False`` (default) the
            *beginning* is preserved (the end is trimmed).  Preserving the
            end is useful for keeping the most recent context in a
            conversation.

    Returns:
        The (possibly truncated) text.  Returns an empty string for
        ``None`` or empty input.  If the text already fits, it is returned
        unchanged.
    """
    if not text:
        return ""

    if max_tokens <= 0:
        return ""

    tokenizer = _get_tokenizer()

    if tokenizer is not None:
        try:
            token_ids = tokenizer.encode(text)

            # Already within budget — return unchanged.
            if len(token_ids) <= max_tokens:
                return text

            if preserve_end:
                # Keep the *last* max_tokens tokens.
                truncated_ids = token_ids[-max_tokens:]
            else:
                # Keep the *first* max_tokens tokens.
                truncated_ids = token_ids[:max_tokens]

            return tokenizer.decode(truncated_ids, skip_special_tokens=True)
        except Exception:  # noqa: BLE001
            logger.warning(
                "GPT-2 tokenizer encode/decode failed during truncation; "
                "falling back to word-based truncation.",
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # Fallback: word-level truncation when the tokenizer is unavailable.
    # ------------------------------------------------------------------
    words = text.split()
    estimated_word_limit = max(1, int(max_tokens / _WORD_TOKEN_RATIO))

    if len(words) <= estimated_word_limit:
        return text

    if preserve_end:
        return " ".join(words[-estimated_word_limit:])
    return " ".join(words[:estimated_word_limit])

"""The LLM client contract every real provider adapter must implement."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, Dict, List

#: A chat message: ``{"role": "system"|"user"|"assistant", "content": "..."}``
Message = Dict[str, str]


def system(content: str) -> Message:
    return {"role": "system", "content": content}


def user(content: str) -> Message:
    return {"role": "user", "content": content}


@dataclass
class LLMResponse:
    """Uniform completion result.

    ``provider`` is the *vendor* identity used by the cross-model red line
    (e.g. ``"openai"``, ``"anthropic"``, ``"google"``), NOT the model name.
    """

    text: str
    tokens: int = 0
    provider: str = ""
    model: str = ""
    usd: float = 0.0
    wall_s: float = 0.0
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "tokens": self.tokens,
            "provider": self.provider,
            "model": self.model,
            "usd": self.usd,
            "wall_s": self.wall_s,
        }


class LLMClient(abc.ABC):
    """Abstract chat-completion client.

    Implement exactly three things to plug a real vendor in:
      * ``provider``  -- vendor id string (drives the cross-model assertion)
      * ``model``     -- concrete model id
      * ``complete()``-- messages -> :class:`LLMResponse`
    """

    #: vendor identity, e.g. "openai" / "anthropic" / "google" / "stub_alpha"
    provider: str = ""
    #: concrete model identity, e.g. "gpt-4.1" / "gemini-2.5-pro"
    model: str = ""

    @abc.abstractmethod
    def complete(self, messages: List[Message], **kw: Any) -> LLMResponse:
        """Run a chat completion and return an :class:`LLMResponse`."""

    # -- convenience -------------------------------------------------------
    def complete_text(self, prompt: str, **kw: Any) -> str:
        return self.complete([user(prompt)], **kw).text

    def describe(self) -> Dict[str, str]:
        return {"provider": self.provider, "model": self.model, "impl": type(self).__name__}

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return "<{} provider={} model={}>".format(type(self).__name__, self.provider, self.model)


class EchoClient(LLMClient):
    """Trivial non-LLM client, handy in tests that only need an identity."""

    def __init__(self, provider: str, model: str = "echo") -> None:
        self.provider = provider
        self.model = model

    def complete(self, messages: List[Message], **kw: Any) -> LLMResponse:
        text = messages[-1]["content"] if messages else ""
        return LLMResponse(text=text, tokens=len(text), provider=self.provider, model=self.model)

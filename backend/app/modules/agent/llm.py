"""The agents' model: an open-source LLM (Gemma by default) served by Ollama.

Gemma has no native tool-calling API, so tool use is done the portable way:
the model is asked for one JSON object, Ollama's JSON mode constrains the
output, and the result is parsed and validated here (and again against the
tool schema in agents.py). Instructions go in the user turn because Gemma
has no system role. Everything runs on this machine; nothing is paid.
"""

import json
import re
from typing import Protocol

from langchain_core.messages import HumanMessage
from langchain_core.output_parsers import StrOutputParser

from app.core.config import settings


class AgentModelUnavailable(Exception):
    """Ollama is not running, the model is missing, or it timed out."""


class AgentLLM(Protocol):
    name: str

    async def json(self, prompt: str) -> dict: ...

    async def text(self, prompt: str) -> str: ...


def model_name() -> str:
    return settings.agent_model or settings.ollama_model


def parse_json_object(text: str) -> dict:
    """First JSON object in the reply; small models sometimes wrap it."""
    text = (text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in the reply")
    value = json.loads(text[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("the reply is not a JSON object")
    return value


class OllamaAgentLLM:
    def __init__(self, model: str | None = None):
        from langchain_ollama import ChatOllama

        self.name = model or model_name()
        common = {"model": self.name, "base_url": settings.ollama_url, "temperature": 0, "client_kwargs": {"timeout": settings.ollama_timeout_seconds}}
        self._json_chain = ChatOllama(format="json", **common) | StrOutputParser()
        self._text_chain = ChatOllama(**common) | StrOutputParser()

    async def _call(self, chain, prompt: str) -> str:
        try:
            return await chain.ainvoke([HumanMessage(content=prompt)])
        except Exception as error:  # connection refused, model not pulled, timeout
            raise AgentModelUnavailable(f"The local model ({self.name}) is not available: {error}") from error

    async def json(self, prompt: str) -> dict:
        reply = await self._call(self._json_chain, prompt)
        try:
            return parse_json_object(reply)
        except (ValueError, json.JSONDecodeError) as error:
            # One repair attempt: show the model its own invalid output.
            repair = f"{prompt}\n\nYour previous reply was not valid JSON ({error}):\n{reply[:800]}\nReply again with ONE valid JSON object only."
            return parse_json_object(await self._call(self._json_chain, repair))

    async def text(self, prompt: str) -> str:
        return (await self._call(self._text_chain, prompt)).strip()

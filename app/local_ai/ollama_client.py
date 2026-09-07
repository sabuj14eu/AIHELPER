"""Ollama HTTP client.

Every failure mode named in the work order is handled explicitly and mapped to
a distinct exception, because the gateway routes on *why* the local model
failed, not merely that it did.
"""

from __future__ import annotations

import time

import httpx

from app.core.errors import ProviderTimeoutError, ProviderUnavailableError
from app.core.logging import get_logger

log = get_logger("ollama")


class OllamaClient:
    def __init__(self, base_url: str, timeout: float = 60.0, client: httpx.Client | None = None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = client

    # ------------------------------------------------------------- plumbing
    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(base_url=self.base_url, timeout=self.timeout)
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def _post(self, path: str, payload: dict, timeout: float | None = None) -> dict:
        try:
            response = self._http().post(path, json=payload, timeout=timeout or self.timeout)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(f"Ollama timed out after {timeout or self.timeout}s") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(f"Ollama unreachable: {type(exc).__name__}") from exc
        if response.status_code == 404:
            # Ollama returns 404 with a "model not found" body for a missing model.
            raise ProviderUnavailableError(
                "Ollama rejected the request (model missing?)",
                detail={"status": 404, "body": response.text[:300]},
            )
        if response.status_code >= 500:
            raise ProviderUnavailableError(
                "Ollama server error", detail={"status": response.status_code}
            )
        if response.status_code >= 400:
            raise ProviderUnavailableError(
                "Ollama refused the request",
                detail={"status": response.status_code, "body": response.text[:300]},
            )
        try:
            return response.json()
        except ValueError as exc:
            raise ProviderUnavailableError("Ollama returned a non-JSON body") from exc

    # ---------------------------------------------------------------- API
    def is_alive(self) -> bool:
        try:
            self._http().get("/api/tags", timeout=min(self.timeout, 5.0)).raise_for_status()
            return True
        except (httpx.HTTPError, httpx.TimeoutException):
            return False

    def list_models(self) -> list[str]:
        """Names of installed models. Returns [] if Ollama is not reachable."""
        try:
            response = self._http().get("/api/tags", timeout=min(self.timeout, 10.0))
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, httpx.TimeoutException, ValueError):
            return []
        return [m.get("name", "") for m in data.get("models", []) if m.get("name")]

    def chat(
        self,
        model: str,
        messages: list[dict],
        *,
        max_tokens: int | None = None,
        temperature: float = 0.2,
        timeout: float | None = None,
        stop: list[str] | None = None,
        json_mode: bool = False,
    ) -> dict:
        options: dict = {"temperature": temperature}
        if max_tokens:
            options["num_predict"] = max_tokens
        if stop:
            options["stop"] = stop
        payload: dict = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": options,
        }
        if json_mode:
            payload["format"] = "json"
        started = time.perf_counter()
        data = self._post("/api/chat", payload, timeout=timeout)
        elapsed_ms = int((time.perf_counter() - started) * 1000)

        content = (data.get("message") or {}).get("content", "")
        if not isinstance(content, str):
            raise ProviderUnavailableError("Ollama returned a malformed message")
        return {
            "text": content,
            "model": data.get("model", model),
            "input_tokens": int(data.get("prompt_eval_count") or 0),
            "output_tokens": int(data.get("eval_count") or 0),
            "latency_ms": elapsed_ms,
            "finish_reason": data.get("done_reason"),
            "raw": {k: v for k, v in data.items() if k != "message"},
        }

    def embed(self, model: str, texts: list[str], timeout: float | None = None) -> list[list[float]]:
        """Embeddings via /api/embed (falls back to the older /api/embeddings)."""
        try:
            data = self._post("/api/embed", {"model": model, "input": texts}, timeout=timeout)
            vectors = data.get("embeddings")
            if isinstance(vectors, list) and vectors:
                return [[float(x) for x in v] for v in vectors]
        except ProviderUnavailableError:
            pass  # older server: fall through to the per-text endpoint
        out: list[list[float]] = []
        for text in texts:
            data = self._post("/api/embeddings", {"model": model, "prompt": text}, timeout=timeout)
            vector = data.get("embedding")
            if not isinstance(vector, list) or not vector:
                raise ProviderUnavailableError("Ollama returned an empty embedding")
            out.append([float(x) for x in vector])
        return out

    def pull(self, model: str, timeout: float = 900.0) -> dict:
        """Download a model. Long-running; used by the admin/model routes."""
        return self._post("/api/pull", {"model": model, "stream": False}, timeout=timeout)

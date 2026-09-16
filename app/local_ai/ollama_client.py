"""Ollama HTTP client.

Every failure mode named in the work order is handled explicitly and mapped to
a distinct exception, because the gateway routes on *why* the local model
failed, not merely that it did.
"""

from __future__ import annotations

import json
import time

import httpx

from app.core.errors import ProviderTimeoutError, ProviderUnavailableError
from app.core.logging import get_logger

log = get_logger("ollama")


# How long Ollama holds a model in memory after the last request. Measured on
# the production box 2026-09-16: loading qwen2.5:7b costs 31.0 s, which landed
# *inside* a request's own timeout budget every time the model had been idle.
# The reload is not the model being slow, it is the model being absent, and an
# assistant that is asked something twice an hour should never pay it.
KEEP_ALIVE = "24h"


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

    def _raise_for(self, status: int, body: str) -> None:
        """Map an Ollama HTTP status onto the exception the gateway routes on."""
        if status == 404:
            # Ollama returns 404 with a "model not found" body for a missing model.
            raise ProviderUnavailableError(
                "Ollama rejected the request (model missing?)",
                detail={"status": 404, "body": body[:300]},
            )
        if status >= 500:
            raise ProviderUnavailableError("Ollama server error", detail={"status": status})
        if status >= 400:
            raise ProviderUnavailableError(
                "Ollama refused the request", detail={"status": status, "body": body[:300]}
            )

    def _post(self, path: str, payload: dict, timeout: float | None = None) -> dict:
        try:
            response = self._http().post(path, json=payload, timeout=timeout or self.timeout)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(f"Ollama timed out after {timeout or self.timeout}s") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(f"Ollama unreachable: {type(exc).__name__}") from exc
        self._raise_for(response.status_code, response.text)
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
        """Generate, streaming internally, and never throw away finished work.

        This used to be one blocking POST with ``stream: false``. When the
        deadline passed, httpx cancelled the request and the client raised --
        so an answer that was 900 tokens along when the clock ran out was lost
        exactly as completely as one that never started. On a CPU box, where
        generation is measured in single-digit tokens per second, that is the
        difference between a usable reply and an empty bubble.

        So the tokens are read as they arrive and kept. The deadline is still
        enforced, and enforced more honestly than before: httpx's timeout is
        per-read, so a slow-but-steady stream could run for an hour without
        ever tripping it. The budget is a wall-clock deadline checked between
        chunks instead.

        A run cut short returns what it has with ``finish_reason="timeout"``.
        That is a partial answer, and the layers above are responsible for
        labelling it as one -- it must never be presented as complete. Only a
        deadline that arrives with *nothing* generated is still a failure.
        """
        options: dict = {"temperature": temperature}
        if max_tokens:
            options["num_predict"] = max_tokens
        if stop:
            options["stop"] = stop
        payload: dict = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": options,
            "keep_alive": KEEP_ALIVE,
        }
        if json_mode:
            payload["format"] = "json"

        budget = timeout or self.timeout
        started = time.perf_counter()
        deadline = started + budget
        parts: list[str] = []
        final: dict = {}
        timed_out = False
        # Kept so a stream that produces nothing still gets the precise
        # diagnosis the blocking call used to give. "no content" would be true
        # of all three of these and useful for none of them.
        saw_line = False
        saw_json = False
        bad_content = False
        # Ollama sends nothing at all while it loads the model and evaluates the
        # prompt; the first frame arrives with the first generated token. So
        # "no frames" and "frames but no text" are different failures with
        # different fixes -- one is the budget being spent before generation
        # starts, the other is the model producing nothing. Saying "timed out"
        # for both is what sent an entire session looking at the wrong number.
        saw_content_frame = False

        try:
            with self._http().stream(
                "POST", "/api/chat", json=payload, timeout=budget
            ) as response:
                if response.status_code >= 400:
                    response.read()
                    self._raise_for(response.status_code, response.text)
                for line in response.iter_lines():
                    if not line.strip():
                        continue
                    saw_line = True
                    try:
                        chunk = json.loads(line)
                    except ValueError:
                        continue  # a partial frame is not a failure
                    saw_json = True
                    if chunk.get("error"):
                        raise ProviderUnavailableError(
                            "Ollama reported an error",
                            detail={"body": str(chunk["error"])[:300]},
                        )
                    piece = (chunk.get("message") or {}).get("content")
                    if isinstance(piece, str):
                        saw_content_frame = True
                        parts.append(piece)
                    elif piece is not None:
                        bad_content = True
                    if chunk.get("done"):
                        final = chunk
                        break
                    if time.perf_counter() >= deadline:
                        timed_out = True
                        log.warning(
                            "local_generation_deadline",
                            model=model,
                            budget_s=round(budget, 1),
                            kept_chars=sum(len(p) for p in parts),
                        )
                        break
        except httpx.TimeoutException as exc:
            timed_out = True
            if not parts:
                raise ProviderTimeoutError(f"Ollama timed out after {budget}s") from exc
        except httpx.HTTPError as exc:
            if not parts:
                raise ProviderUnavailableError(
                    f"Ollama unreachable: {type(exc).__name__}"
                ) from exc
            timed_out = True

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        text = "".join(parts)

        if not text.strip():
            # Nothing usable came back. Each of these is a different fault with
            # a different fix, so they keep their own message.
            if bad_content:
                raise ProviderUnavailableError("Ollama returned a malformed message")
            if timed_out:
                # The clock ran out with nothing written. There is no partial
                # answer to keep, so this is a failure and the router routes on it.
                if not saw_content_frame:
                    raise ProviderTimeoutError(
                        f"Ollama timed out after {budget}s without starting to "
                        "generate — the whole budget went on loading the model and "
                        "reading the prompt, so shortening the prompt is the fix, "
                        "not a longer clock"
                    )
                raise ProviderTimeoutError(f"Ollama timed out after {budget}s")
            if saw_line and not saw_json:
                raise ProviderUnavailableError("Ollama returned a non-JSON body")
            if not final:
                raise ProviderUnavailableError("Ollama returned no content")

        return {
            "text": text,
            "model": final.get("model", model),
            "input_tokens": int(final.get("prompt_eval_count") or 0),
            "output_tokens": int(final.get("eval_count") or 0),
            "latency_ms": elapsed_ms,
            "finish_reason": "timeout" if timed_out else final.get("done_reason"),
            "raw": {k: v for k, v in final.items() if k != "message"},
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

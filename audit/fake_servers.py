"""Protocol-faithful stand-ins for Ollama and Anthropic.

Why these exist, stated plainly so the audit is not misread:

The unit tests fake the *Provider* objects. That proves the routing logic but
skips the HTTP client, the model manager, the request/response shapes and the
error mapping. These servers fake the *wire protocol* instead, so the real
`OllamaClient`, `OllamaProvider`, `ModelManager`, `AnthropicProvider` and the
whole runtime wiring execute exactly as they would in production.

What is still simulated: the neural network. There are no model weights here.
The "local model" answers from a small rule — it can restate a fact that is in
its prompt, and it cannot answer a hard question that is not. That is a
faithful model of the property the system depends on (a small local model is
only as good as its context) and it is the property the cost-saving cycle
rests on, but it is a simulation and this report says so wherever it matters.
"""

from __future__ import annotations

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

# A question the "local model" cannot answer unaided.
HARD_TOPIC = "health contribution look-back"

PAID_ANSWER = (
    "Under the flat tax the health contribution for a month is 4.9% of the income of the "
    "month before it, and the contribution year runs from 1 February to 31 January, so "
    "January is settled on the previous year's figures."
)


class _Handler(BaseHTTPRequestHandler):
    server_version = "FakeOllama/1.0"

    def log_message(self, *_args):
        pass  # keep the demo output readable

    def _json(self, status: int, body: dict) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _read(self) -> dict:
        length = int(self.headers.get("content-length", 0))
        return json.loads(self.rfile.read(length) or b"{}")


class OllamaHandler(_Handler):
    """Speaks the real Ollama API: /api/tags, /api/chat, /api/embed."""

    MODELS = ["llama3.2:3b", "llama3.2:1b", "qwen2.5:7b", "nomic-embed-text"]

    def do_GET(self):  # noqa: N802 - stdlib naming
        if self.path == "/api/tags":
            self.server.calls.append(("tags", None))
            self._json(200, {"models": [{"name": m, "size": 1} for m in self.MODELS]})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):  # noqa: N802
        body = self._read()
        if self.path == "/api/chat":
            self._chat(body)
        elif self.path in ("/api/embed", "/api/embeddings"):
            self._embed(body)
        else:
            self._json(404, {"error": f"unknown path {self.path}"})

    def _chat(self, body: dict) -> None:
        if self.server.offline:
            self.connection.close()
            return
        messages = body.get("messages", [])
        user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        self.server.calls.append(("chat", body.get("model")))

        has_context = "<<<CONTEXT" in user
        if HARD_TOPIC.lower() in user.lower() and not has_context:
            text = "INSUFFICIENT_CONTEXT — I do not have the rules for this."
        elif has_context:
            block = user[user.find("<<<CONTEXT") : user.find("CONTEXT>>>")]
            lines = [ln for ln in block.splitlines()[1:] if ln.strip()]
            text = "Based on the stored answer: " + " ".join(lines).strip()
        elif "capital of france" in user.lower():
            text = "The capital of France is Paris."
        else:
            text = "Here is a clear, complete answer to your question, stated plainly."

        self._json(
            200,
            {
                "model": body.get("model", "llama3.2:3b"),
                "message": {"role": "assistant", "content": text},
                "done": True,
                "done_reason": "stop",
                "prompt_eval_count": max(1, len(user) // 4),
                "eval_count": max(1, len(text) // 4),
            },
        )

    def _embed(self, body: dict) -> None:
        """A deterministic 768-dim embedding with real lexical structure.

        Not a neural embedder — it is a hashed bag of words widened to the
        dimension a real model would return. It exercises the embedding code
        path and the Qdrant/database dimension handling; it does not prove
        anything about semantic quality.
        """
        import hashlib
        import math

        inputs = body.get("input") or [body.get("prompt", "")]
        if isinstance(inputs, str):
            inputs = [inputs]
        self.server.calls.append(("embed", body.get("model")))

        vectors = []
        for text in inputs:
            vector = [0.0] * 768
            words = re.findall(r"[A-Za-z0-9_]+", (text or "").lower())
            bigrams = [f"{a}_{b}" for a, b in zip(words, words[1:], strict=False)]
            for word in words + bigrams:
                digest = hashlib.blake2b(word.encode(), digest_size=8).digest()
                index = int.from_bytes(digest[:4], "big") % 768
                vector[index] += 1.0 if digest[4] & 1 else -1.0
            norm = math.sqrt(sum(v * v for v in vector)) or 1.0
            vectors.append([v / norm for v in vector])
        self._json(200, {"embeddings": vectors})


class AnthropicHandler(_Handler):
    """Speaks the real Anthropic Messages API."""

    def do_POST(self):  # noqa: N802
        body = self._read()
        if not self.path.endswith("/messages"):
            self._json(404, {"error": "not found"})
            return
        if not self.headers.get("x-api-key"):
            self._json(401, {"error": {"message": "missing x-api-key"}})
            return

        turns = body.get("messages", [])
        prompt = "\n".join(m.get("content", "") for m in turns)
        self.server.calls.append(
            {
                "model": body.get("model"),
                "prompt": prompt,
                "system": body.get("system", ""),
                "max_tokens": body.get("max_tokens"),
            }
        )
        self._json(
            200,
            {
                "id": f"msg_{len(self.server.calls):06d}",
                "type": "message",
                "role": "assistant",
                "model": body.get("model", "claude-sonnet-5"),
                "content": [{"type": "text", "text": PAID_ANSWER}],
                "stop_reason": "end_turn",
                "usage": {
                    "input_tokens": max(1, len(prompt) // 4),
                    "output_tokens": max(1, len(PAID_ANSWER) // 4),
                },
            },
        )


class FakeServer:
    def __init__(self, handler, port: int, bind: str = "127.0.0.1"):
        # bind="0.0.0.0" lets containers reach these through host.docker.internal,
        # which is how the containerised persistence audit drives them.
        self.httpd = HTTPServer((bind, port), handler)
        self.bind = bind
        self.httpd.calls = []
        self.httpd.offline = False
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.port = port

    def start(self) -> FakeServer:
        self.thread.start()
        return self

    @property
    def calls(self) -> list:
        return self.httpd.calls

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def set_offline(self, value: bool) -> None:
        self.httpd.offline = value

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()

"""Non-blocking Ollama client with bounded generation and safe error messages."""
import asyncio
import httpx


class OllamaError(Exception):
    """An actionable error safe to display to the user."""


class OllamaClient:
    def __init__(self, url: str, model: str, timeout: float = 120, context_length: int = 8192):
        self.url = url
        self.model = model
        self.timeout = timeout
        self.context_length = context_length
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=5), trust_env=False)

    async def close(self) -> None:
        await self.client.aclose()

    async def chat(self, messages: list[dict[str, str]]) -> str:
        try:
            async with asyncio.timeout(self.timeout):
                response = await self.client.post(self.url, json={
                    "model": self.model, "messages": messages, "stream": False,
                    "think": False,
                    "options": {"num_ctx": self.context_length, "num_predict": -1},
                })
                response.raise_for_status()
        except (httpx.TimeoutException, TimeoutError) as exc:
            raise OllamaError("Ollama timed out. Try again with a shorter request.") from exc
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status == 404:
                message = "Model or endpoint not found: check OLLAMA_MODEL, OLLAMA_URL and your installed models."
            else:
                message = f"Ollama returned HTTP error {status}. Try again later."
            raise OllamaError(message) from exc
        except httpx.RequestError as exc:
            raise OllamaError("Unable to connect to Ollama. Check that it is running and reachable.") from exc
        try:
            data = response.json()
            content = data["message"]["content"]
            if not isinstance(content, str) or not content.strip() or data.get("error"):
                raise ValueError
        except (ValueError, KeyError, TypeError) as exc:
            raise OllamaError("Ollama returned an empty or invalid response.") from exc
        return content.strip()

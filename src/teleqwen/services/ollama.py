import logging
import httpx


class OllamaError(Exception):
    pass

async def chat(messages: list[dict], tools: list[dict], url: str, model: str) -> dict:
    logging.info("Sending request to Ollama")
    try:
        async with httpx.AsyncClient(timeout=120, trust_env=False) as client:
            response = await client.post(url, json={
                "model": model,
                "messages": messages,
                "tools": tools,
                "stream": False,
                "think": False,
                "options": {
                    "num_ctx": 4096,
                    "num_predict": 512
                },
            })
            response.raise_for_status()

        message = response.json()["message"]

        if not isinstance(message, dict):
            raise ValueError("Invalid message")

        if not message.get("content") and not message.get("tool_calls"):
            raise ValueError("Empty response")

        logging.info("Ollama response received")
        return message

    except httpx.HTTPError as exc:
        raise OllamaError(
            "Cannot reach Ollama or use this model."
        ) from exc

    except (ValueError, KeyError, TypeError) as exc:
        raise OllamaError(
            "Ollama returned an empty or invalid response."
        ) from exc
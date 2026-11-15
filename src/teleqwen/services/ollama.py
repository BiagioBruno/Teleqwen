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

        if not isinstance(message, dict) or message.get("role") != "assistant":
            raise ValueError("Invalid message")

        content = message.get("content", "")
        tool_calls = message.get("tool_calls", [])
        if not isinstance(content, str) or not isinstance(tool_calls, list):
            raise ValueError("Invalid content or tool calls")
        if not content.strip() and not tool_calls:
            raise ValueError("Empty response")

        for tool_call in tool_calls:
            if not isinstance(tool_call, dict):
                raise ValueError("Invalid tool call")
            function = tool_call.get("function")
            if not isinstance(function, dict):
                raise ValueError("Invalid tool function")
            name = function.get("name")
            if not isinstance(name, str) or not name.strip():
                raise ValueError("Invalid tool name")
            if not isinstance(function.get("arguments"), dict):
                raise ValueError("Invalid tool arguments")

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

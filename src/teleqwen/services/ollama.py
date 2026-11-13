import httpx


class OllamaError(Exception):
    pass


async def chat(messages: list[dict[str, str]], url: str, model: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=120, trust_env=False) as client:
            response = await client.post(url, json={
                "model": model,
                "messages": messages,
                "stream": False,
                "think": False,
                "options": {"num_ctx": 4096, "num_predict": 512},
            })
            response.raise_for_status()
        answer = response.json()["message"]["content"]
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError
        return answer.strip()
    except httpx.HTTPError as exc:
        raise OllamaError("Cannot reach Ollama or use this model. Check that Ollama is running and the model is installed.") from exc
    except (ValueError, KeyError, TypeError) as exc:
        raise OllamaError("Ollama returned an empty or invalid response. Try again.") from exc

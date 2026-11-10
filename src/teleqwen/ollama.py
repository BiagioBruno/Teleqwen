import requests

def send_message(url: str, message: str) -> str:
    response = requests.post(
        url,
        json={
            "model": "qwen3.5:2b",
            "messages": [
                {"role": "user", "content": message}
            ],
            "stream": False,
        },
        timeout=120,
    )
    response.raise_for_status()
    return response.json()

def handle_ollama_comunication(url: str, message: str) -> str:
    try:
        data = send_message(url, message)
        msg = data["message"]["content"]

    except requests.exceptions.Timeout:
        msg = "Ollama did not respond within the expected time"

    except requests.exceptions.ConnectionError:
        msg = "Unable to connect to Ollama"

    except requests.exceptions.HTTPError as error:
        msg = f"HTTP error: {error}, Server error: {response.text}"

    except requests.exceptions.JSONDecodeError:
        msg = "The server returned a response that is not valid JSON"

    except requests.exceptions.RequestException as error:
        msg = f"Error during the request: {error}"

    except (KeyError, TypeError):
        msg = "The received JSON does not have the expected structure"

    return msg
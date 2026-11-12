"""Check Ollama before polling Telegram and manage only processes we start."""
import logging
import os
import shutil
import subprocess
import time
from contextlib import contextmanager
from urllib.parse import urlsplit, urlunsplit

import httpx

logger = logging.getLogger(__name__)


class OllamaStartupError(Exception):
    """An actionable startup failure without private server details."""


def _models(client: httpx.Client, url: str) -> list[str] | None:
    try:
        response = client.get(url)
    except (httpx.ConnectError, httpx.TimeoutException):
        return None
    except httpx.RequestError as exc:
        raise OllamaStartupError("Unable to check Ollama. Check OLLAMA_URL.") from exc
    if response.status_code != 200:
        raise OllamaStartupError(f"Ollama's model endpoint returned HTTP {response.status_code}. Check OLLAMA_URL.")
    try:
        models = response.json()["models"]
        if not isinstance(models, list):
            raise ValueError
        names = [model["name"] for model in models]
        if not all(isinstance(name, str) for name in names):
            raise ValueError
        return names
    except (ValueError, KeyError, TypeError) as exc:
        raise OllamaStartupError("The server did not return a valid Ollama model list. Check OLLAMA_URL.") from exc


def _stop(process: subprocess.Popen) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


@contextmanager
def ensure_ollama(url: str, model: str, startup_timeout: float = 20):
    """Reuse an existing service, or run a local one until Teleqwen exits."""
    parsed = urlsplit(url)
    tags_url = urlunsplit((parsed.scheme, parsed.netloc, "/api/tags", "", ""))
    process = None
    try:
        with httpx.Client(timeout=.5, trust_env=False) as client:
            names = _models(client, tags_url)
            if names is None:
                if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
                    raise OllamaStartupError("Ollama is unreachable. Automatic startup supports local HTTP addresses only; start your configured server manually.")
                executable = shutil.which("ollama")
                if executable is None:
                    raise OllamaStartupError("Ollama is not installed or is not on PATH. Install it from https://ollama.com/download, then restart Teleqwen.")
                env = os.environ.copy()
                # Bind to the configured loopback address, ignoring any inherited host.
                host = f"[{parsed.hostname}]" if parsed.hostname == "::1" else parsed.hostname
                env["OLLAMA_HOST"] = f"{host}:{parsed.port or 80}"
                env.pop("TELEGRAM_BOT_TOKEN", None)
                logger.info("Starting local Ollama service...")
                try:
                    process = subprocess.Popen(
                        [executable, "serve"], env=env, stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        start_new_session=True,
                    )
                except OSError as exc:
                    raise OllamaStartupError("Unable to start Ollama. Try running 'ollama serve' manually.") from exc
                deadline = time.monotonic() + startup_timeout
                while time.monotonic() < deadline:
                    names = _models(client, tags_url)
                    if names is not None:
                        break
                    if process.poll() is not None:
                        raise OllamaStartupError("Ollama exited during startup. Run 'ollama serve' manually to see the error.")
                    time.sleep(.25)
                else:
                    raise OllamaStartupError("Ollama did not become ready in time. Try running 'ollama serve' manually.")
            expected = model if ":" in model.rsplit("/", 1)[-1] else f"{model}:latest"
            if model not in names and expected not in names:
                raise OllamaStartupError(f"Model '{model}' is not installed. Start Ollama and run 'ollama pull {model}', then restart Teleqwen.")
        logger.info("Ollama is ready. Starting Telegram bot...")
        yield
    finally:
        if process is not None:
            _stop(process)

import logging
from teleqwen.agent.tool_registry import ToolRegistry
from teleqwen.services.ollama import chat
from teleqwen.storage.history import History
from teleqwen.config import Settings


class agent:    
    def __init__(self, settings: Settings):
        logging.info("Create Agent")
        self.settings = settings
        self.action_in_progress = False
        self.tools = ToolRegistry().tools
        self.history = History(settings.history_file)

    async def handle_prompt(self, text: str) -> str:
        messages = self.history.prompt(text)
        tool_registry = ToolRegistry()

        MAX_ITERATIONS = 10

        for _ in range(MAX_ITERATIONS):
            response = await chat(messages, self.tools, self.settings.ollama_url, self.settings.model)

            # Save assistant response
            messages.append(response)

            # No tool calls: final answer
            if not response.get("tool_calls"):
                logging.info("No tool calls requested; using the model's reply")
                answer = response.get("content", "")
                self.history.append(text, answer)
                return answer

            # Execute requested tools
            for tool_call in response["tool_calls"]:
                name = tool_call["function"]["name"]
                arguments = tool_call["function"]["arguments"]
                try:
                    logging.info("Executing tool: %s", name)
                    result = tool_registry.execute(name, arguments)
                except Exception as exc:
                    result = f"Tool execution failed: {exc}"
                    logging.exception("Tool execution failed: %s", name)

                # Send tool result back to Qwen
                messages.append({
                    "role": "tool",
                    "tool_name": name,
                    "content": str(result)
                })

        raise RuntimeError("Agent exceeded maximum iterations")

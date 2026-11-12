"""English command menu and onboarding text."""
from teleqwen.storage.history import MAX_CONVERSATIONS

COMMANDS = (
    ("start", "Show the welcome message"),
    ("help", "List all features"),
    ("ask", "Ask a question: /ask question"),
    ("new", "Start a new conversation"),
    ("chats", "List saved conversations"),
    ("delete", "Delete a conversation: /delete ID"),
    ("clear", "Delete all conversations: /clear confirm"),
)
WELCOME = "Hello! I am Teleqwen, your local assistant.\nUse /help to list all features."
HELP = f"""Teleqwen features:
/start — show the welcome message
/help — list all features
/ask question — send a question to the assistant
/new — start a new conversation
/chats — list local conversations (up to {MAX_CONVERSATIONS})
/delete ID — delete a local conversation
/clear confirm — delete all your local conversations
You can also send a regular message to talk to the assistant.
I keep up to {MAX_CONVERSATIONS} conversations, including the active one. Creating another conversation at the limit deletes the oldest one.
Local deletion removes the bot's memory; messages on Telegram remain visible."""

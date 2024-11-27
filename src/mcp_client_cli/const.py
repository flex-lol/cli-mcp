from pathlib import Path

CACHE_EXPIRY_HOURS = 24
DEFAULT_QUERY = "Summarize https://www.youtube.com/watch?v=NExtKbS1Ljc"
CONFIG_FILE = 'mcp-server-config.json'
CONFIG_DIR = Path.home() / ".llm"
SQLITE_DB = CONFIG_DIR / "conversations.db"
CACHE_DIR = CONFIG_DIR / "mcp-tools"
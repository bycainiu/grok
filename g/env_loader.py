"""Environment loader for register configuration."""
from pathlib import Path
from dotenv import load_dotenv


def load_register_env() -> None:
    """Load .env.register when present, otherwise fall back to .env."""
    project_root = Path(__file__).resolve().parents[1]
    register_env = project_root / ".env.register"
    if register_env.exists():
        load_dotenv(dotenv_path=register_env, override=False)
    else:
        load_dotenv()

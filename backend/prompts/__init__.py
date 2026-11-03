"""Version-controlled prompt resources."""
from importlib.resources import files

def load_prompt(name: str) -> str:
    if not name or "/" in name or "\\" in name or name.startswith("."):
        raise ValueError("Expected a prompt resource filename")
    return files(__package__).joinpath(name).read_text(encoding="utf-8")

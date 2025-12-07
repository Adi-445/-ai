import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SEARCH_SCRIPT = BASE_DIR / "search.sh"


def run(query: str) -> str:
    if not SEARCH_SCRIPT.exists():
        return "search.sh missing"
    proc = subprocess.run([str(SEARCH_SCRIPT), query], capture_output=True, text=True, check=False)
    return proc.stdout.strip() or proc.stderr.strip()


def main():
    if len(sys.argv) < 2:
        print("Usage: python main.py <query>")
        raise SystemExit(1)
    query = " ".join(sys.argv[1:])
    print(run(query))


if __name__ == "__main__":
    main()

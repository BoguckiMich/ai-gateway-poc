"""Pre-commit: szuka sekretow w dodawanych liniach (reguly z gateway/security.py)."""
import subprocess
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gateway.security import RULES  # noqa: E402

SECRET_RULES = [(n, rx) for n, rx in RULES if n != "prompt_injection"]


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout


problems = []
for f in git("diff", "--cached", "--name-only").splitlines():
    name = f.rsplit("/", 1)[-1]
    if name == ".env" or (name.startswith(".env.") and name != ".env.example"):
        problems.append(f"{f}: plik ze zmiennymi srodowiskowymi")
for line in git("diff", "--cached", "-U0").splitlines():
    if line.startswith("+") and not line.startswith("+++"):
        for name, rx in SECRET_RULES:
            if rx.search(line):
                problems.append(f"wykryto {name}: {line[1:60]}...")

if problems:
    print("COMMIT ZABLOKOWANY - znaleziono sekrety:\n  " + "\n  ".join(problems))
    sys.exit(1)

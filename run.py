import os

import uvicorn

from gateway.main import create_app

# Wczytaj .env jesli istnieje (bez dodatkowych zaleznosci)
if os.path.exists(".env"):
    for line in open(".env", encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

app = create_app()

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("PORT", "8080")))

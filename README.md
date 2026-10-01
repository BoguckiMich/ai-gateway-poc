# DRO AI Gateway

Lekkie proxy (FastAPI + httpx) między programistami a API Anthropic: autoryzacja kluczami gateway, skan promptów, limity tokenów, audit log.

## Start

```
python -m venv .venv
.venvScriptsctivate
pip install -r requirements.txt
copy .env.example .env     # uzupelnij ANTHROPIC_API_KEY i GATEWAY_KEYS
python run.py              # http://127.0.0.1:8080
```

## Uzycie w istniejacym projekcie

```python
client = anthropic.Anthropic(base_url="http://127.0.0.1:8080", api_key="<klucz-gateway>")
```
albo bez zmian w kodzie: `ANTHROPIC_BASE_URL=http://127.0.0.1:8080` i `ANTHROPIC_API_KEY=<klucz-gateway>`.

## Co robi

- **Auth**: klucz gateway -> klient; prawdziwy klucz Anthropic zna tylko gateway. Bez `GATEWAY_KEYS` dziala jako passthrough.
- **Bezpieczenstwo** (`gateway/security.py`): blokuje wycieki kluczy (Anthropic/OpenAI/AWS/GitHub, klucze prywatne) i proste prompt injection. `GATEWAY_MODE=monitor` tylko loguje.
- **Tokeny**: wstepne oszacowanie (heurystyka lub dokladnie przez `count_tokens`), limit `MAX_INPUT_TOKENS`, dzienny budzet `DAILY_TOKEN_LIMIT` na klienta (429). Rzeczywiste zuzycie z odpowiedzi, takze dla streamingu SSE.
- **Observability**: `audit.jsonl` (klient, model, tokeny, cache, latencja, blokady), `GET /admin/usage`, `GET /healthz`.
- Wszystkie inne endpointy `/v1/*` sa przekazywane bez zmian.

## Testy

`python -m pytest`

## Uwagi

- `/admin/usage` nie ma jeszcze autoryzacji - przed wystawieniem poza localhost dodaj ja.
- Zliczanie wczytuje budzet z `audit.jsonl` po restarcie; przy kilku procesach potrzebna bedzie wspolna baza (np. Redis/SQLite).

## Ochrona przed wyciekiem kluczy

`.env` jest w `.gitignore`, a hook pre-commit (`scripts/hooks`) blokuje commit z sekretami lub plikiem `.env`. Po sklonowaniu repo wlacz go: `git config core.hooksPath scripts/hooks`.

### Klucz Anthropic

Prawdziwy `ANTHROPIC_API_KEY` najlepiej trzymac poza repo, jako zmienna uzytkownika: `setx ANTHROPIC_API_KEY "sk-ant-..."` (nowy terminal). Zmienna srodowiskowa ma pierwszenstwo nad `.env`, a klucz nigdy nie trafia do logow ani odpowiedzi gateway.

# Runbook — provider credentials

**Never paste a credential into a chat, a ticket, a commit or a shell history
file.** Everything below is designed so the value only ever exists in
`/opt/seolead/.env` (mode 600, git-ignored) and in the provider's own dashboard.

## Check current status

```bash
docker exec seolead_api seolead credentials
```

Reports `CONFIGURED` / `NOT_CONFIGURED` per provider. It never prints a value, a
prefix or a length — a report that leaks four characters of a key is still a leak.

## Adding a credential safely

Run these **on the VPS, as the operator**. The `read -s` form keeps the value off
the terminal and out of shell history; the leading space in `HISTCONTROL` terms is
belt and braces.

### DataForSEO

Get the API **password** (not your account password) from
`https://app.dataforseo.com/api-access`.

```bash
cd /opt/seolead

# 1. Login — not secret, but keep the same method for consistency.
read -r -p "DataForSEO login: " DFS_LOGIN

# 2. Password — never echoed.
read -r -s -p "DataForSEO API password: " DFS_PASS; echo

# 3. Write into .env without printing either value.
python3 - "$DFS_LOGIN" "$DFS_PASS" <<'PY'
import pathlib, re, sys
login, password = sys.argv[1], sys.argv[2]
path = pathlib.Path(".env"); text = path.read_text()
for key, value in (("DATAFORSEO_LOGIN", login), ("DATAFORSEO_PASSWORD", password)):
    line = f"{key}={value}"
    text = (re.sub(rf"^{key}=.*$", line, text, flags=re.M)
            if re.search(rf"^{key}=", text, re.M) else text + f"\n{line}\n")
path.write_text(text)
print(f"{key} written (value not printed)")
PY

# 4. Clear the variables from this shell.
unset DFS_LOGIN DFS_PASS

chmod 600 .env
```

### Tavily

Key from `https://app.tavily.com` (starts `tvly-`).

```bash
cd /opt/seolead
read -r -s -p "Tavily API key: " TAVILY_KEY; echo
python3 - "$TAVILY_KEY" <<'PY'
import pathlib, re, sys
path = pathlib.Path(".env"); text = path.read_text()
line = f"TAVILY_API_KEY={sys.argv[1]}"
text = (re.sub(r"^TAVILY_API_KEY=.*$", line, text, flags=re.M)
        if re.search(r"^TAVILY_API_KEY=", text, re.M) else text + f"\n{line}\n")
path.write_text(text)
print("TAVILY_API_KEY written (value not printed)")
PY
unset TAVILY_KEY
chmod 600 .env
```

### OpenAI

Key from `https://platform.openai.com/api-keys` (starts `sk-`).

```bash
cd /opt/seolead
read -r -s -p "OpenAI API key: " OPENAI_KEY; echo
python3 - "$OPENAI_KEY" <<'PY'
import pathlib, re, sys
path = pathlib.Path(".env"); text = path.read_text()
line = f"SEOLEAD_LLM_API_KEY={sys.argv[1]}"
text = (re.sub(r"^SEOLEAD_LLM_API_KEY=.*$", line, text, flags=re.M)
        if re.search(r"^SEOLEAD_LLM_API_KEY=", text, re.M) else text + f"\n{line}\n")
path.write_text(text)
print("SEOLEAD_LLM_API_KEY written (value not printed)")
PY
unset OPENAI_KEY
chmod 600 .env
```

The model is separate configuration and is **not** a secret:

```bash
sed -i 's|^SEOLEAD_LLM_MODEL=.*|SEOLEAD_LLM_MODEL=gpt-4o|' .env
```

## Apply and verify

```bash
cd /opt/seolead
docker compose up -d seolead_api      # picks up the new .env
sleep 5
docker exec seolead_api seolead credentials
```

Expect `CONFIGURED` for the providers you added and
`"ready_for_live_test": true` once all three are in place.

## Cost before you start

| Provider | Billing | Notes |
|---|---|---|
| DataForSEO | ~$0.002 per live advanced SERP call; prepaid balance | returns its actual cost on every response, which we record |
| Tavily | credits, monthly plan | returns **no** monetary cost — spend is tracked as unknown |
| OpenAI | per token | tokens recorded per draft; no price table configured yet |

Per-job ceilings are enforced before any request:
`SEOLEAD_MAX_CALLS_PER_PROVIDER` (default 3). A runaway loop hits
`PROVIDER_BUDGET_EXCEEDED`, not an invoice.

Freshness caching means a repeated query does not re-pay:

| Research | TTL | Env |
|---|---|---|
| SERP | 24 h | `SEOLEAD_SERP_TTL_HOURS` |
| Web research | 168 h | `SEOLEAD_WEB_RESEARCH_TTL_HOURS` |
| Community | 72 h | `SEOLEAD_COMMUNITY_TTL_HOURS` |

## Rotation

Replace the value with the same procedure and restart `seolead_api`. Nothing
caches a credential in memory across a restart, and no credential is written to
any image layer.

## If a credential leaks

1. Revoke it in the provider dashboard **first** — before editing anything here.
2. Issue a new one and write it with the procedure above.
3. `docker compose up -d seolead_api`.
4. Check `git log -p -- .env` returns nothing (`.env` is git-ignored; this
   confirms it was never committed).

## What is verified about handling

- `.env` is git-ignored, mode 600, and a test asserts `.env.example` contains no
  key-shaped values.
- Log output passes a redactor covering `key=value`, `"key": "value"` and bare
  `sk-` / `ghp_` tokens, applied to both message and exception text.
- DataForSEO's Basic header is built by `httpx` from `auth=(login, password)`; the
  credential is never assembled into a string this code logs.
- Provider error messages are bounded and tested not to echo the credential.
- Health and credential endpoints return statuses only.

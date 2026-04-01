# MTA Integration Overview

tobira provides plugins for the most popular mail transfer agents. Each plugin queries the tobira API server via HTTP and maps the ML spam score to MTA-native scoring symbols.

## Supported MTAs

| MTA | Plugin Language | Difficulty | Status |
|-----|----------------|:----------:|--------|
| [rspamd](rspamd.md) | Lua | Low | Stable |
| [SpamAssassin](spamassassin.md) | Perl | Medium | Stable |
| [Haraka](haraka.md) | Node.js | Low | Stable |
| [Postfix milter](postfix-milter.md) | Python | Medium | Stable |

!!! tip "Already using rspamd GPT?"
    If you're running rspamd's GPT module with Ollama, tobira can fine-tune a custom model for higher accuracy with minimal changes. See the [rspamd GPT Migration Guide](../handson/rspamd-gpt-migration.md).

## How It Works

All MTA plugins follow the same pattern:

1. **Intercept** — The plugin hooks into the MTA's message processing pipeline
2. **Extract** — Email body (and optionally headers) are extracted
3. **Query** — An HTTP POST request is sent to `POST /predict` on the tobira API server
4. **Score** — The ML spam probability is mapped to tiered symbols/rules

## Score Mapping

All plugins use consistent symbol names and weights:

| ML Score | Symbol | Weight | Meaning |
|----------|--------|--------|---------|
| >= 0.9 | `TOBIRA_SPAM_HIGH` | +8.0 | High confidence spam |
| >= 0.7 | `TOBIRA_SPAM_MED` | +5.0 | Medium confidence spam |
| >= 0.5 | `TOBIRA_SPAM_LOW` | +2.0 | Low confidence spam |
| < 0.3 | `TOBIRA_HAM` | -3.0 | Likely legitimate |

## Fail-Open Mode

All plugins support fail-open mode: if the tobira API server is unreachable or returns an error, the email is passed through without ML scoring. This ensures mail delivery is never blocked by an ML service outage.

## Prerequisites

Before integrating with your MTA, ensure:

1. The tobira API server is running and accessible from the MTA host
2. The `/health` endpoint returns `{"status": "ok"}`
3. Network connectivity between MTA and API server (same host or private network recommended)

```bash
# Verify API server health
curl http://127.0.0.1:8000/health
```

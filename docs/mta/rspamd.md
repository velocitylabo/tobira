# rspamd Integration

This guide covers integrating tobira with rspamd using the Lua HTTP plugin.

## Prerequisites

- rspamd >= 3.0
- tobira API server running and accessible

## Installation

1. Copy the plugin and configuration files:

    ```bash
    sudo cp integrations/rspamd/tobira.lua /etc/rspamd/local.d/
    sudo cp integrations/rspamd/tobira.conf /etc/rspamd/local.d/
    ```

2. Edit the configuration file `/etc/rspamd/local.d/tobira.conf`:

    ```
    tobira {
      api_url = "http://127.0.0.1:8000/predict";
      timeout = 2.0;
      fail_open = true;
      send_headers = false;
      max_size = 65536;

      symbols {
        spam_high = "TOBIRA_SPAM_HIGH";
        spam_med = "TOBIRA_SPAM_MED";
        spam_low = "TOBIRA_SPAM_LOW";
        ham = "TOBIRA_HAM";
      }

      thresholds {
        high = 0.9;
        med = 0.7;
        low = 0.5;
        ham = 0.3;
      }

      weights {
        spam_high = 8.0;
        spam_med = 5.0;
        spam_low = 2.0;
        ham = -3.0;
      }
    }
    ```

3. Test the configuration and reload:

    ```bash
    rspamadm configtest
    sudo systemctl reload rspamd
    ```

## Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `api_url` | `http://127.0.0.1:8000/predict` | tobira API endpoint URL |
| `timeout` | `2.0` | HTTP request timeout in seconds |
| `fail_open` | `true` | Pass mail through on API errors |
| `send_headers` | `false` | Send email headers for header-based scoring |
| `max_size` | `65536` | Maximum email text size in bytes |

## Header Analysis

Enable `send_headers = true` to include email authentication headers (SPF, DKIM, DMARC) and sender information in the classification request. This can improve accuracy for borderline cases.

```
tobira {
  send_headers = true;
}
```

When enabled, the plugin extracts and sends:

- SPF, DKIM, DMARC authentication results
- From and Reply-To addresses
- Received headers
- Content-Type

## Verification

Check that the plugin is loaded:

```bash
rspamadm configdump | grep tobira
```

Send a test email and check the rspamd log:

```bash
# Check rspamd logs for tobira symbols
sudo journalctl -u rspamd | grep TOBIRA
```

## Troubleshooting

**Plugin not loading**: Ensure `tobira.lua` is in `/etc/rspamd/local.d/` and has correct permissions.

**Timeout errors**: Increase the `timeout` value or check network connectivity to the API server.

**No symbols added**: Verify the API server is returning valid responses with `curl`:

```bash
curl -X POST http://127.0.0.1:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"text": "Test email content"}'
```

## Upgrading from rspamd GPT

If you're already using rspamd's GPT module (`gpt.lua`) with Ollama, tobira can fine-tune a custom model on your email data for significantly higher accuracy. See the [rspamd GPT Migration Guide](../handson/rspamd-gpt-migration.md) for a step-by-step walkthrough.

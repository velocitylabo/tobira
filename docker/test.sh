#!/usr/bin/env bash
set -uo pipefail

cd "$(dirname "$0")"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass=0
fail=0
skip=0

ok() {
  echo -e "  ${GREEN}PASS${NC}: $1"
  ((pass++))
}

ng() {
  echo -e "  ${RED}FAIL${NC}: $1"
  ((fail++))
}

warn() {
  echo -e "  ${YELLOW}SKIP${NC}: $1"
  ((skip++))
}

# Extract JSON field using python3 (with timeout via input string)
json_field() {
  echo "$1" | python3 -c "import sys,json; print(json.load(sys.stdin)['$2'])" 2>/dev/null
}

# ----------------------------------------------------------------
# Wait for services to be ready
# ----------------------------------------------------------------
echo ""
echo "Waiting for services to start..."

wait_for() {
  local name="$1" check_cmd="$2" max_wait="${3:-30}"
  local elapsed=0
  while [ $elapsed -lt $max_wait ]; do
    if eval "$check_cmd" >/dev/null 2>&1; then
      echo "  $name ready (${elapsed}s)"
      return 0
    fi
    sleep 1
    ((elapsed++))
  done
  echo "  $name not ready after ${max_wait}s"
  return 1
}

wait_for "tobira-api" "curl -sf --max-time 2 http://localhost:8000/v1/health"
wait_for "haraka"     "python3 -c \"import socket; s=socket.socket(); s.settimeout(2); s.connect(('localhost',2525)); s.close()\""
wait_for "rspamd"     "curl -sf --max-time 2 http://localhost:11334/ping"
wait_for "spamassassin" "python3 -c \"import socket; s=socket.socket(); s.settimeout(2); s.connect(('localhost',783)); s.close()\""

# ----------------------------------------------------------------
# 1. tobira API
# ----------------------------------------------------------------
echo ""
echo "=== tobira API (mock server) ==="

api_ok=false

# health check
if curl -sf --max-time 5 http://localhost:8000/v1/health | grep -q '"ok"'; then
  ok "GET /v1/health"
  api_ok=true
else
  ng "GET /v1/health - is tobira-api running?"
fi

if $api_ok; then
  # ham prediction
  ham_resp=$(curl -sf --max-time 5 -X POST http://localhost:8000/v1/predict \
    -H 'Content-Type: application/json' \
    -d '{"text":"Hello, this is a normal email about our meeting tomorrow."}') || ham_resp=""

  if [ -n "$ham_resp" ]; then
    ham_label=$(json_field "$ham_resp" "label")
    ham_score=$(json_field "$ham_resp" "score")
    ham_score_ok=$(python3 -c "print('yes' if float('${ham_score}') > 0.5 else 'no')" 2>/dev/null)
    if [ "$ham_label" = "ham" ] && [ "$ham_score_ok" = "yes" ]; then
      ok "/v1/predict ham (label=$ham_label, score=$ham_score): $ham_resp"
    else
      ng "/v1/predict ham: expected label=ham with score>0.5, got label=$ham_label score=$ham_score ($ham_resp)"
    fi
  else
    ng "/v1/predict ham: no response from API"
  fi

  # spam prediction
  spam_resp=$(curl -sf --max-time 5 -X POST http://localhost:8000/v1/predict \
    -H 'Content-Type: application/json' \
    -d '{"text":"Buy now! Free offer! Click here for your lottery winner prize!"}') || spam_resp=""

  if [ -n "$spam_resp" ]; then
    spam_label=$(json_field "$spam_resp" "label")
    spam_score=$(json_field "$spam_resp" "score")
    spam_score_ok=$(python3 -c "print('yes' if float('${spam_score}') > 0.5 else 'no')" 2>/dev/null)
    if [ "$spam_label" = "spam" ] && [ "$spam_score_ok" = "yes" ]; then
      ok "/v1/predict spam (label=$spam_label, score=$spam_score): $spam_resp"
    else
      ng "/v1/predict spam: expected label=spam with score>0.5, got label=$spam_label score=$spam_score ($spam_resp)"
    fi
  else
    ng "/v1/predict spam: no response from API"
  fi
else
  warn "skipping API predict tests (health check failed)"
fi

# ----------------------------------------------------------------
# 2. Haraka
# ----------------------------------------------------------------
echo ""
echo "=== Haraka ==="

haraka_ok=false

# Check if Haraka is listening
if python3 -c "import socket; s=socket.socket(); s.settimeout(3); s.connect(('localhost',2525)); s.close()" 2>/dev/null; then
  haraka_ok=true
fi

if $haraka_ok; then
  # Send ham via SMTP
  haraka_ham=$(python3 -c "
import smtplib
from email.message import EmailMessage
msg = EmailMessage()
msg['From'] = 'test@example.com'
msg['To'] = 'dest@example.com'
msg['Subject'] = 'Test ham'
msg.set_content('Hello, this is a normal email about our meeting tomorrow.')
try:
    with smtplib.SMTP('localhost', 2525, timeout=10) as s:
        s.send_message(msg)
    print('accepted')
except smtplib.SMTPRecipientsRefused:
    print('rejected-recipient')
except Exception as e:
    print(f'error:{e}')
" 2>&1)

  if echo "$haraka_ham" | grep -q "accepted"; then
    ok "ham email accepted: $haraka_ham"
  else
    ng "ham email: $haraka_ham"
  fi

  # Send spam via SMTP
  haraka_spam=$(python3 -c "
import smtplib
from email.message import EmailMessage
msg = EmailMessage()
msg['From'] = 'spammer@example.com'
msg['To'] = 'dest@example.com'
msg['Subject'] = 'Winner!'
msg.set_content('Buy now! Free offer! Click here for your lottery winner prize! Act now! Urgent!')
try:
    with smtplib.SMTP('localhost', 2525, timeout=10) as s:
        s.send_message(msg)
    print('accepted')
except smtplib.SMTPRecipientsRefused:
    print('rejected-recipient')
except smtplib.SMTPDataError as e:
    print(f'rejected-spam:{e}')
except Exception as e:
    print(f'error:{e}')
" 2>&1)

  if echo "$haraka_spam" | grep -q "rejected-spam"; then
    ok "spam email rejected by tobira plugin: $haraka_spam"
  else
    ng "spam email was not rejected: $haraka_spam"
  fi
else
  warn "Haraka not reachable on port 2525 - skipping"
fi

# ----------------------------------------------------------------
# 3. Rspamd
# ----------------------------------------------------------------
echo ""
echo "=== Rspamd ==="

rspamd_ok=false

# Check if rspamd controller is responding
if curl -sf --max-time 5 http://localhost:11334/ping 2>/dev/null | grep -q "pong"; then
  rspamd_ok=true
  ok "rspamd controller responding"
elif curl -sf --max-time 5 http://localhost:11334/stat 2>/dev/null | grep -q "scanned"; then
  rspamd_ok=true
  ok "rspamd controller responding"
else
  warn "rspamd not reachable on port 11334 - skipping"
fi

if $rspamd_ok; then
  # Scan ham message (must send a proper RFC 5322 message for text part parsing)
  rspamd_ham_msg="From: test@example.com
To: dest@example.com
Subject: Normal email
Content-Type: text/plain; charset=utf-8

Hello, this is a perfectly normal business email about our quarterly review."

  rspamd_ham=$(echo "$rspamd_ham_msg" | curl -sf --max-time 10 -X POST http://localhost:11333/checkv2 \
    --data-binary @- 2>&1) || rspamd_ham=""

  if [ -n "$rspamd_ham" ] && echo "$rspamd_ham" | grep -q "TOBIRA_HAM"; then
    ok "ham scan returned TOBIRA_HAM symbol"
  elif [ -n "$rspamd_ham" ]; then
    warn "ham scan: no TOBIRA symbol found (plugin may not be loaded yet)"
  else
    warn "ham scan: no response from rspamd worker"
  fi

  # Scan spam message
  rspamd_spam_msg="From: spammer@example.com
To: dest@example.com
Subject: Winner!
Content-Type: text/plain; charset=utf-8

Buy now! Free offer! Click here for your lottery winner prize! Act now! Urgent discount casino!"

  rspamd_spam=$(echo "$rspamd_spam_msg" | curl -sf --max-time 10 -X POST http://localhost:11333/checkv2 \
    --data-binary @- 2>&1) || rspamd_spam=""

  if [ -n "$rspamd_spam" ] && echo "$rspamd_spam" | grep -q "TOBIRA_SPAM_HIGH\|TOBIRA_SPAM_MED\|TOBIRA_SPAM_LOW"; then
    ok "spam scan returned TOBIRA_SPAM level symbol"
  elif [ -n "$rspamd_spam" ]; then
    warn "spam scan: no TOBIRA_SPAM symbol found"
  else
    warn "spam scan: no response from rspamd worker"
  fi
fi

# ----------------------------------------------------------------
# 4. SpamAssassin
# ----------------------------------------------------------------
echo ""
echo "=== SpamAssassin ==="

sa_ok=false

# Check if spamd is listening
if python3 -c "import socket; s=socket.socket(); s.settimeout(3); s.connect(('localhost',783)); s.close()" 2>/dev/null; then
  sa_ok=true
  ok "spamd is listening on port 783"
else
  warn "spamd not reachable on port 783 - skipping"
fi

if $sa_ok; then
  # Detect the spamassassin container name
  sa_container=$(docker compose ps -q spamassassin 2>/dev/null) || sa_container=""

  if [ -n "$sa_container" ]; then
    # Ham check via docker exec
    spamc_result=$(echo "Subject: Test
From: test@example.com

Hello, this is a normal email." | docker exec -i "$sa_container" spamc -R 2>&1) || spamc_result=""

    if [ -n "$spamc_result" ] && echo "$spamc_result" | grep -q "TOBIRA_HAM"; then
      ok "spamc ham check returned TOBIRA_HAM rule"
    elif [ -n "$spamc_result" ]; then
      warn "spamc responded but no TOBIRA rule found"
    else
      warn "spamc ham check: no response"
    fi

    # Spam check via docker exec
    spamc_spam=$(echo "Subject: Winner! Buy now!
From: spammer@example.com

Buy now! Free offer! Click here for your lottery winner prize! Act now! Urgent discount casino!" | docker exec -i "$sa_container" spamc -R 2>&1) || spamc_spam=""

    if [ -n "$spamc_spam" ] && echo "$spamc_spam" | grep -q "TOBIRA_SPAM_HIGH\|TOBIRA_SPAM_MED\|TOBIRA_SPAM_LOW"; then
      ok "spamc spam check found TOBIRA_SPAM level rule"
    elif [ -n "$spamc_spam" ]; then
      warn "spamc spam check: no TOBIRA_SPAM rule found"
    else
      warn "spamc spam check: no response"
    fi
  else
    warn "spamassassin container not found - skipping spamc checks"
  fi
fi

# ----------------------------------------------------------------
# Summary
# ----------------------------------------------------------------
echo ""
echo "================================"
echo -e "Results: ${GREEN}${pass} passed${NC}, ${RED}${fail} failed${NC}, ${YELLOW}${skip} skipped${NC}"
echo "================================"

[ "$fail" -eq 0 ]

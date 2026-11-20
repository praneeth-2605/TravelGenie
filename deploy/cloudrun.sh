#!/usr/bin/env bash
# Deploy TravelGenie to Google Cloud Run.
#
#   bash deploy/cloudrun.sh            # first deploy: asks for your keys (hidden input)
#   bash deploy/cloudrun.sh            # later: redeploys new code, keeps the saved keys
#   bash deploy/cloudrun.sh --secrets  # re-enter / change keys
#
# Run it from Google Cloud Shell (shell.cloud.google.com), which has gcloud built in.
# Keys are passed to Cloud Run as environment variables through a temporary file
# that is deleted afterwards; they are never written into the repository.
set -euo pipefail

SERVICE="${SERVICE:-travelgenie}"
REGION="${REGION:-asia-southeast1}"   # Singapore; pick the region closest to your Neon database

cd "$(dirname "$0")/.."

PROJECT="$(gcloud config get-value project 2>/dev/null || true)"
if [[ -z "$PROJECT" || "$PROJECT" == "(unset)" ]]; then
  echo "No Google Cloud project selected. Run: gcloud config set project YOUR_PROJECT_ID" >&2
  exit 1
fi
echo "Project: $PROJECT · Region: $REGION · Service: $SERVICE"

echo "Enabling the required Google Cloud APIs (first time only)…"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com --quiet

ask_secrets=false
if [[ "${1:-}" == "--secrets" ]]; then
  ask_secrets=true
elif ! gcloud run services describe "$SERVICE" --region "$REGION" >/dev/null 2>&1; then
  ask_secrets=true   # first deploy
fi

ENV_ARGS=()
if $ask_secrets; then
  ENV_FILE="$(mktemp)"
  chmod 600 "$ENV_FILE"
  trap 'rm -f "$ENV_FILE"' EXIT

  read_secret() {  # read_secret NAME "prompt" required|optional
    local value=""
    read -r -s -p "$2: " value; echo
    if [[ -z "$value" && "$3" == "required" ]]; then echo "$1 is required." >&2; exit 1; fi
    if [[ -n "$value" ]]; then
      # JSON strings are valid YAML, so any characters in the value are safe.
      printf '%s: %s\n' "$1" "$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$value")" >> "$ENV_FILE"
    fi
  }

  echo "Paste each value and press Enter (input is hidden)."
  read_secret DATABASE_URL "Neon connection string (postgresql://…)" required
  read_secret GROQ_API_KEY "Groq API key (gsk_…)" required
  read_secret OPENWEATHERMAP_API_KEY "OpenWeatherMap API key (optional, Enter to skip)" optional
  read_secret TAVILY_API_KEY "Tavily API key (optional, Enter to skip)" optional
  read_secret GOOGLE_CLIENT_ID "Google OAuth Client ID (optional, Enter to skip)" optional
  # A fresh random key that signs login sessions.
  printf 'SECRET_KEY: %s\n' "$(python3 -c 'import json,secrets; print(json.dumps(secrets.token_urlsafe(48)))')" >> "$ENV_FILE"
  ENV_ARGS=(--env-vars-file "$ENV_FILE")
else
  echo "Service exists: deploying new code and keeping its saved keys."
fi

gcloud run deploy "$SERVICE" \
  --source . \
  --region "$REGION" \
  --allow-unauthenticated \
  --memory 2Gi --cpu 1 --cpu-boost \
  --min-instances 0 --max-instances 2 \
  --concurrency 40 --timeout 300 \
  --quiet \
  ${ENV_ARGS[@]+"${ENV_ARGS[@]}"}

URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format 'value(status.url)')"
echo
echo "✅ TravelGenie is live: $URL"

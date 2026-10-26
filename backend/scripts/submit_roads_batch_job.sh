#!/usr/bin/env bash
set -euo pipefail

JOB_ID="prepare-osm-roads-$(date +%Y%m%d-%H%M%S)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/batch_prepare_roads.json"

echo "Submitting Google Cloud Batch job ${JOB_ID} in us-east1..."
gcloud batch jobs submit "${JOB_ID}" \
  --project="geodashing-v2" \
  --location="us-east1" \
  --config="${CONFIG_FILE}" \
  --quiet

echo "Cloud Batch job ${JOB_ID} submitted successfully."
echo "Track status with: gcloud batch jobs describe ${JOB_ID} --project=geodashing-v2 --location=us-east1"

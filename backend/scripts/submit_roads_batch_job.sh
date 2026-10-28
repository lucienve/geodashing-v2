#!/usr/bin/env bash
set -euo pipefail

JOB_ID="prepare-osm-roads-$(date +%Y%m%d-%H%M%S)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/batch_prepare_roads.json"
BUCKET_URI="gs://geodashing-v2-map-data/batch/geodashing-roads-bundle.tar.gz"

BUNDLE_TAR="$(mktemp /tmp/geodashing-roads-bundle-XXXXXX.tar.gz)"
trap 'rm -f "${BUNDLE_TAR}"' EXIT

echo "Packaging local road preparation bundle from ${REPO_ROOT}..."
tar -czf "${BUNDLE_TAR}" -C "${REPO_ROOT}" \
  .python-version \
  pyproject.toml \
  uv.lock \
  backend/scripts/prepare_roads.py

echo "Uploading hermetic code bundle to ${BUCKET_URI}..."
gcloud storage cp "${BUNDLE_TAR}" "${BUCKET_URI}" \
  --project="geodashing-v2" \
  --quiet

echo "Submitting Google Cloud Batch job ${JOB_ID} in us-east1..."
gcloud batch jobs submit "${JOB_ID}" \
  --project="geodashing-v2" \
  --location="us-east1" \
  --config="${CONFIG_FILE}" \
  --quiet

echo "Cloud Batch job ${JOB_ID} submitted successfully."
echo "Track status with: gcloud batch jobs describe ${JOB_ID} --project=geodashing-v2 --location=us-east1"

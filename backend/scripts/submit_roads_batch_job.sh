#!/usr/bin/env bash
set -euo pipefail

FORCE_FLAG=""
SKIP_BUILD=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --force)
      FORCE_FLAG="true"
      shift
      ;;
    --skip-image-build)
      SKIP_BUILD="true"
      shift
      ;;
    *)
      echo "Usage: $0 [--force] [--skip-image-build]" >&2
      exit 1
      ;;
  esac
done

JOB_ID="prepare-osm-roads-$(date +%Y%m%d-%H%M%S)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/batch_prepare_roads.json"
DOCKERFILE_PATH="${SCRIPT_DIR}/Dockerfile.prepare_roads"
IMAGE_TAG="us-east1-docker.pkg.dev/geodashing-v2/batch/prepare-roads:latest"

BUILD_CTX="$(mktemp -d /tmp/geodashing-roads-build-XXXXXX)"
trap 'rm -rf "${BUILD_CTX}"' EXIT

SUBMIT_CONFIG="${CONFIG_FILE}"
if [[ -n "${FORCE_FLAG}" ]]; then
  echo "Force flag enabled: injecting --force into batch job container commands..."
  SUBMIT_CONFIG="${BUILD_CTX}/batch_prepare_roads.json"
  python3 -c '
import json, sys
with open(sys.argv[1], "r", encoding="utf-8") as f:
    data = json.load(f)
commands = data["taskGroups"][0]["taskSpec"]["runnables"][0]["container"]["commands"]
if "--force" not in commands:
    commands.append("--force")
with open(sys.argv[2], "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
' "${CONFIG_FILE}" "${SUBMIT_CONFIG}"
fi

echo "Staging hermetic build context from ${REPO_ROOT} into ${BUILD_CTX}..."
cp "${REPO_ROOT}/.python-version" "${BUILD_CTX}/"
cp "${REPO_ROOT}/pyproject.toml" "${BUILD_CTX}/"
cp "${REPO_ROOT}/uv.lock" "${BUILD_CTX}/"
mkdir -p "${BUILD_CTX}/backend/scripts"
cp "${REPO_ROOT}/backend/__init__.py" "${BUILD_CTX}/backend/"
cp "${REPO_ROOT}/backend/scripts/__init__.py" "${BUILD_CTX}/backend/scripts/"
cp "${REPO_ROOT}/backend/scripts/prepare_roads.py" "${BUILD_CTX}/backend/scripts/"
cp "${REPO_ROOT}/backend/scripts/prepare_water.py" "${BUILD_CTX}/backend/scripts/"

if [[ -z "${SKIP_BUILD}" ]]; then
  echo "Configuring Docker authentication for Artifact Registry in us-east1..."
  gcloud auth configure-docker us-east1-docker.pkg.dev --quiet

  echo "Building container image ${IMAGE_TAG}..."
  docker build \
    -f "${DOCKERFILE_PATH}" \
    -t "${IMAGE_TAG}" \
    "${BUILD_CTX}"

  echo "Pushing container image to Artifact Registry..."
  docker push "${IMAGE_TAG}"
else
  echo "Skipping container image build and push (--skip-image-build enabled)."
fi

echo "Submitting Google Cloud Batch job ${JOB_ID} in us-east1..."
gcloud batch jobs submit "${JOB_ID}" \
  --project="geodashing-v2" \
  --location="us-east1" \
  --config="${SUBMIT_CONFIG}" \
  --quiet

echo "Cloud Batch job ${JOB_ID} submitted successfully."
echo "Track status with: gcloud batch jobs describe ${JOB_ID} --project=geodashing-v2 --location=us-east1"

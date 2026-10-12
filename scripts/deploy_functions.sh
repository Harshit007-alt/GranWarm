#!/bin/bash
set -euo pipefail

CLUSTER_NAME="granuwarm-local"
FUNCTIONS_DIR="functions"

echo "=== GranuWarm: Deploy all functions ==="
echo ""

# Collect function folders
FOLDERS=$(ls -d ${FUNCTIONS_DIR}/f*/ 2>/dev/null | sort)
if [ -z "$FOLDERS" ]; then
  echo "ERROR: no function folders found in ${FUNCTIONS_DIR}/"
  exit 1
fi

COUNT=0
FAILED=0

for dir in $FOLDERS; do
  name=$(basename "$dir")
  tag="granuwarm/${name}:v1"

  echo "-----------------------------------------"
  echo "[$((COUNT+1))] $name"
  echo "-----------------------------------------"

  # 1. Build
  if ! docker build -t "$tag" "$dir"; then
    echo "  BUILD FAILED: $name"
    FAILED=$((FAILED+1))
    continue
  fi

  # 2. Load into kind
  if ! kind load docker-image "$tag" --name "$CLUSTER_NAME"; then
    echo "  LOAD FAILED: $name"
    FAILED=$((FAILED+1))
    continue
  fi

  # 3. Patch service.yaml with imagePullPolicy if missing
  svc_yaml="${dir}service.yaml"
  if [ -f "$svc_yaml" ]; then
    if ! grep -q "imagePullPolicy" "$svc_yaml"; then
      sed -i '/- image:/a\          imagePullPolicy: IfNotPresent' "$svc_yaml"
      echo "  patched imagePullPolicy"
    fi
  else
    echo "  WARNING: $svc_yaml not found"
    FAILED=$((FAILED+1))
    continue
  fi

  # 4. Apply Knative Service
  if ! kubectl apply -f "$svc_yaml"; then
    echo "  APPLY FAILED: $name"
    FAILED=$((FAILED+1))
    continue
  fi

  COUNT=$((COUNT+1))
  echo "  OK"
  echo ""
done

echo "========================================="
echo "Deployed: $COUNT   Failed: $FAILED"
echo "========================================="
echo ""
echo "Waiting 15s for pods to schedule..."
sleep 15

echo ""
echo "=== Knative services ==="
kubectl get ksvc

echo ""
echo "=== Pods in default namespace ==="
kubectl get pods

echo ""
echo "=== Memory headroom ==="
free -h
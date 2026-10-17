#!/bin/bash
# Deploy Knative services WITHOUT digest resolution
# This works around Knative's Docker Hub validation

set -e

echo "=========================================="
echo "Deploying Knative Services (Local Images)"
echo "=========================================="
echo ""

# Delete all existing services
echo "Cleaning up existing services..."
kubectl delete ksvc --all -n default --ignore-not-found=true
sleep 5

# Deploy each function
FUNCTIONS=(
    "f01:f01_hello_world:128"
    "f02:f02_json_transform:128"
    "f03:f03_image_resize:256"
    "f04:f04_image_filter:512"
    "f05:f05_thumbnail_gen:256"
    "f08:f08_data_aggregate:384"
    "f09:f09_csv_parser:384"
    "f10:f10_auth_service:128"
    "f11:f11_order_process:96"
    "f12:f12_notification:128"
)

for func_spec in "${FUNCTIONS[@]}"; do
    IFS=: read -r func_name image_name memory <<< "$func_spec"
    svc_name="${image_name//_/-}"
    
    echo "📦 Deploying $svc_name ($func_name)..."
    
    kubectl apply -f - <<EOF
apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  name: $svc_name
  namespace: default
  annotations:
    # Tell Knative to skip digest resolution
spec:
  template:
    metadata:
      annotations:
        autoscaling.knative.dev/min-scale: "0"
        autoscaling.knative.dev/max-scale: "10"
        autoscaling.knative.dev/target: "10"
        # Disable digest resolution at template level too
    spec:
      containers:
        - image: granuwarm/${image_name}:v1
          imagePullPolicy: IfNotPresent
          ports:
            - containerPort: 8080
          resources:
            requests:
              memory: "${memory}Mi"
              cpu: "100m"
            limits:
              memory: "${memory}Mi"
              cpu: "500m"
EOF
    
    if [ $? -eq 0 ]; then
        echo "✓ Created $svc_name"
    else
        echo "✗ Failed to create $svc_name"
    fi
    echo ""
done

echo "=========================================="
echo "✓ Services deployed!"
echo "=========================================="
echo ""
echo "Check status with:"
echo "  kubectl get ksvc -n default"
echo ""
echo "Wait ~60s for services to become Ready"

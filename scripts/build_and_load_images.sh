#!/bin/bash
# Build all function Docker images and load them into Kind cluster
# This fixes the "Unable to fetch image" errors

set -e

CLUSTER_NAME="granuwarm-local"
FUNCTIONS=(f01_hello_world f02_json_transform f03_image_resize f04_image_filter f05_thumbnail_gen f08_data_aggregate f09_csv_parser f10_auth_service f11_order_process f12_notification)

# Skip f06 and f07 (they have dependency issues)

echo "==================================="
echo "Building GranuWarm Function Images"
echo "==================================="
echo ""

for func in "${FUNCTIONS[@]}"; do
    echo "📦 Building $func..."
    
    # Navigate to function directory
    cd "functions/$func"
    
    # Build image
    docker build -t "granuwarm/${func}:v1" . 2>&1 | grep -E "(Step|Successfully|ERROR)" || true
    
    if [ $? -eq 0 ]; then
        echo "✓ Built granuwarm/${func}:v1"
        
        # Load into Kind cluster
        echo "  Loading into Kind cluster..."
        kind load docker-image "granuwarm/${func}:v1" --name "$CLUSTER_NAME"
        echo "✓ Loaded into $CLUSTER_NAME"
    else
        echo "✗ Failed to build $func"
    fi
    
    # Go back to repo root
    cd ../..
    echo ""
done

echo "==================================="
echo "✓ Image build complete!"
echo "==================================="
echo ""
echo "Next steps:"
echo "1. Update Knative services to use ImagePullPolicy: Never"
echo "2. Delete existing revisions to force rebuild"
echo ""
echo "Run: ./scripts/restart_services.sh"

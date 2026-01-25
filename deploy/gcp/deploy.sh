#!/bin/bash
# Cloud Run Deployment Script for CartPilot
# Builds Docker images, pushes to Artifact Registry, and deploys to Cloud Run

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Load configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

if [ -f "$SCRIPT_DIR/config.env" ]; then
    source "$SCRIPT_DIR/config.env"
else
    echo -e "${RED}Error: config.env not found. Please run setup.sh first.${NC}"
    exit 1
fi

# Service configuration
SERVICES=("merchant-a" "merchant-b" "cartpilot-api" "cartpilot-mcp")
SERVICE_PORTS=(8001 8002 8000 8003)

# Secrets (should be set via environment or Secret Manager)
CARTPILOT_API_KEY="${CARTPILOT_API_KEY:-}"
WEBHOOK_SECRET="${WEBHOOK_SECRET:-}"

# Function to print colored output
info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    if ! command -v docker &> /dev/null; then
        error "Docker is not installed"
        exit 1
    fi
    
    if ! command -v gcloud &> /dev/null; then
        error "gcloud CLI is not installed"
        exit 1
    fi
    
    if ! docker info > /dev/null 2>&1; then
        error "Docker daemon is not running"
        exit 1
    fi
    
    gcloud config set project "$GCP_PROJECT_ID" > /dev/null 2>&1
    success "Using project: $GCP_PROJECT_ID"
}

# Build and push Docker image
build_and_push_image() {
    local service=$1
    local image_name="$ARTIFACT_REGISTRY_URL/$service"
    local service_dir="$PROJECT_ROOT/$service"
    
    info "Building image for $service..."
    
    if [ ! -d "$service_dir" ]; then
        error "Service directory not found: $service_dir"
        return 1
    fi
    
    # Build image
    docker build -t "$image_name:latest" "$service_dir" || {
        error "Failed to build image for $service"
        return 1
    }
    
    # Tag with commit hash if available
    local commit_hash=$(git rev-parse --short HEAD 2>/dev/null || echo "latest")
    docker tag "$image_name:latest" "$image_name:$commit_hash" || true
    
    # Push image
    info "Pushing image to Artifact Registry..."
    docker push "$image_name:latest" || {
        error "Failed to push image for $service"
        return 1
    }
    
    docker push "$image_name:$commit_hash" 2>/dev/null || true
    
    success "Image pushed: $image_name:latest"
    export "${service//-/_}_IMAGE"="$image_name:latest"
}

# Deploy merchant service to Cloud Run
deploy_merchant_service() {
    local service=$1
    local port=$2
    local merchant_id="${service//merchant-/}"
    local image_name="${ARTIFACT_REGISTRY_URL}/${service}:latest"
    local service_name="$service"
    
    info "Deploying $service to Cloud Run..."
    
    # Get CartPilot API URL (will be set after API deployment)
    local cartpilot_api_url="${CARTPILOT_API_URL:-}"
    
    # Prepare environment variables
    local env_vars=(
        "MERCHANT_ID=$merchant_id"
        "LOG_LEVEL=INFO"
    )
    
    if [ "$service" = "merchant-b" ]; then
        env_vars+=("CHAOS_ENABLED=false")
    fi
    
    # Deploy to Cloud Run
    gcloud run deploy "$service_name" \
        --image="$image_name" \
        --platform=managed \
        --region="$GCP_REGION" \
        --allow-unauthenticated \
        --port="$port" \
        --memory=512Mi \
        --cpu=1 \
        --min-instances=0 \
        --max-instances=10 \
        --timeout=300 \
        --set-env-vars=$(IFS=,; echo "${env_vars[*]}") \
        --project="$GCP_PROJECT_ID" || {
        error "Failed to deploy $service"
        return 1
    }
    
    # Get service URL
    local service_url=$(gcloud run services describe "$service_name" \
        --region="$GCP_REGION" \
        --project="$GCP_PROJECT_ID" \
        --format="value(status.url)")
    
    success "$service deployed: $service_url"
    export "${service//-/_}_URL"="$service_url"
    
    # Update webhook URL after CartPilot API is deployed
    if [ -n "$cartpilot_api_url" ]; then
        info "Updating webhook URL for $service..."
        gcloud run services update "$service_name" \
            --region="$GCP_REGION" \
            --update-env-vars="WEBHOOK_URL=${cartpilot_api_url}/webhooks/merchant,WEBHOOK_SECRET=${WEBHOOK_SECRET}" \
            --project="$GCP_PROJECT_ID" || true
    fi
}

# Deploy CartPilot API to Cloud Run
deploy_api_service() {
    local service="cartpilot-api"
    local image_name="${ARTIFACT_REGISTRY_URL}/${service}:latest"
    local service_name="$service"
    
    info "Deploying CartPilot API to Cloud Run..."
    
    # Check if Cloud SQL connection is configured
    if [ -z "${CLOUDSQL_CONNECTION_NAME:-}" ]; then
        error "Cloud SQL not configured. Please run deploy-cloudsql.sh first."
        exit 1
    fi
    
    # Get merchant URLs
    local merchant_a_url="${MERCHANT_A_URL:-}"
    local merchant_b_url="${MERCHANT_B_URL:-}"
    
    if [ -z "$merchant_a_url" ] || [ -z "$merchant_b_url" ]; then
        warning "Merchant URLs not set. Deploying merchants first..."
        # This will be handled by deployment order
    fi
    
    # Prepare environment variables
    local env_vars=(
        "DATABASE_URL=${CLOUDSQL_DATABASE_URL}"
        "CARTPILOT_API_KEY=${CARTPILOT_API_KEY}"
        "WEBHOOK_SECRET=${WEBHOOK_SECRET}"
        "MERCHANT_A_URL=${merchant_a_url}"
        "MERCHANT_A_ID=merchant-a"
        "MERCHANT_A_ENABLED=true"
        "MERCHANT_B_URL=${merchant_b_url}"
        "MERCHANT_B_ID=merchant-b"
        "MERCHANT_B_ENABLED=true"
        "LOG_LEVEL=INFO"
        "DEBUG=false"
        "SEED_CATALOG=false"
    )
    
    # Deploy to Cloud Run with Cloud SQL connection
    gcloud run deploy "$service_name" \
        --image="$image_name" \
        --platform=managed \
        --region="$GCP_REGION" \
        --allow-unauthenticated \
        --port=8000 \
        --memory=1Gi \
        --cpu=1 \
        --min-instances=0 \
        --max-instances=10 \
        --timeout=300 \
        --add-cloudsql-instances="$CLOUDSQL_CONNECTION_NAME" \
        --set-env-vars=$(IFS=,; echo "${env_vars[*]}") \
        --service-account="$GCP_SERVICE_ACCOUNT" \
        --project="$GCP_PROJECT_ID" || {
        error "Failed to deploy CartPilot API"
        return 1
    }
    
    # Get service URL
    local service_url=$(gcloud run services describe "$service_name" \
        --region="$GCP_REGION" \
        --project="$GCP_PROJECT_ID" \
        --format="value(status.url)")
    
    success "CartPilot API deployed: $service_url"
    export CARTPILOT_API_URL="$service_url"
    
    # Update merchant webhook URLs
    if [ -n "${MERCHANT_A_URL:-}" ]; then
        info "Updating webhook URL for merchant-a..."
        gcloud run services update merchant-a \
            --region="$GCP_REGION" \
            --update-env-vars="WEBHOOK_URL=${service_url}/webhooks/merchant,WEBHOOK_SECRET=${WEBHOOK_SECRET}" \
            --project="$GCP_PROJECT_ID" || true
    fi
    
    if [ -n "${MERCHANT_B_URL:-}" ]; then
        info "Updating webhook URL for merchant-b..."
        gcloud run services update merchant-b \
            --region="$GCP_REGION" \
            --update-env-vars="WEBHOOK_URL=${service_url}/webhooks/merchant,WEBHOOK_SECRET=${WEBHOOK_SECRET}" \
            --project="$GCP_PROJECT_ID" || true
    fi
}

# Deploy MCP server to Cloud Run
deploy_mcp_service() {
    local service="cartpilot-mcp"
    local image_name="${ARTIFACT_REGISTRY_URL}/${service}:latest"
    local service_name="$service"
    
    info "Deploying MCP server to Cloud Run..."
    
    # Get CartPilot API URL
    local cartpilot_api_url="${CARTPILOT_API_URL:-}"
    
    if [ -z "$cartpilot_api_url" ]; then
        error "CartPilot API URL not set. Deploy API first."
        exit 1
    fi
    
    # Prepare environment variables
    local env_vars=(
        "CARTPILOT_API_URL=${cartpilot_api_url}"
        "CARTPILOT_API_KEY=${CARTPILOT_API_KEY}"
        "TRANSPORT=sse"
        "SSE_HOST=0.0.0.0"
        "SSE_PORT=8003"
        "LOG_LEVEL=INFO"
    )
    
    # Deploy to Cloud Run
    gcloud run deploy "$service_name" \
        --image="$image_name" \
        --platform=managed \
        --region="$GCP_REGION" \
        --allow-unauthenticated \
        --port=8003 \
        --memory=512Mi \
        --cpu=1 \
        --min-instances=0 \
        --max-instances=10 \
        --timeout=300 \
        --set-env-vars=$(IFS=,; echo "${env_vars[*]}") \
        --project="$GCP_PROJECT_ID" || {
        error "Failed to deploy MCP server"
        return 1
    }
    
    # Get service URL
    local service_url=$(gcloud run services describe "$service_name" \
        --region="$GCP_REGION" \
        --project="$GCP_PROJECT_ID" \
        --format="value(status.url)")
    
    success "MCP server deployed: $service_url"
    export MCP_URL="$service_url"
}

# Build all images
build_all_images() {
    info "Building and pushing all Docker images..."
    echo ""
    
    for service in "${SERVICES[@]}"; do
        build_and_push_image "$service"
        echo ""
    done
    
    success "All images built and pushed"
}

# Deploy all services in correct order
deploy_all_services() {
    info "Deploying services to Cloud Run..."
    echo ""
    
    # Step 1: Deploy merchants (no dependencies)
    info "Step 1: Deploying merchant services..."
    deploy_merchant_service "merchant-a" 8001
    export MERCHANT_A_URL="${MERCHANT_A_URL:-}"
    echo ""
    
    deploy_merchant_service "merchant-b" 8002
    export MERCHANT_B_URL="${MERCHANT_B_URL:-}"
    echo ""
    
    # Step 2: Deploy CartPilot API (depends on merchants and Cloud SQL)
    info "Step 2: Deploying CartPilot API..."
    deploy_api_service
    echo ""
    
    # Step 3: Deploy MCP server (depends on API)
    info "Step 3: Deploying MCP server..."
    deploy_mcp_service
    echo ""
    
    success "All services deployed"
}

# Display deployment summary
show_summary() {
    echo ""
    echo "=========================================="
    success "Deployment completed!"
    echo "=========================================="
    echo ""
    
    info "Service URLs:"
    
    local merchant_a_url=$(gcloud run services describe merchant-a \
        --region="$GCP_REGION" \
        --project="$GCP_PROJECT_ID" \
        --format="value(status.url)" 2>/dev/null || echo "N/A")
    echo "  Merchant A:     $merchant_a_url"
    
    local merchant_b_url=$(gcloud run services describe merchant-b \
        --region="$GCP_REGION" \
        --project="$GCP_PROJECT_ID" \
        --format="value(status.url)" 2>/dev/null || echo "N/A")
    echo "  Merchant B:      $merchant_b_url"
    
    local api_url=$(gcloud run services describe cartpilot-api \
        --region="$GCP_REGION" \
        --project="$GCP_PROJECT_ID" \
        --format="value(status.url)" 2>/dev/null || echo "N/A")
    echo "  CartPilot API:   $api_url"
    
    local mcp_url=$(gcloud run services describe cartpilot-mcp \
        --region="$GCP_REGION" \
        --project="$GCP_PROJECT_ID" \
        --format="value(status.url)" 2>/dev/null || echo "N/A")
    echo "  MCP Server:      $mcp_url"
    echo ""
    
    info "MCP SSE Endpoint: ${mcp_url}/sse"
    echo ""
    info "Test the deployment:"
    echo "  curl ${api_url}/health"
    echo ""
}

# Main execution
main() {
    local build_only=false
    local deploy_only=false
    
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --build-only)
                build_only=true
                shift
                ;;
            --deploy-only)
                deploy_only=true
                shift
                ;;
            *)
                error "Unknown option: $1"
                echo "Usage: $0 [--build-only|--deploy-only]"
                exit 1
                ;;
        esac
    done
    
    echo ""
    echo "=========================================="
    echo "  CartPilot Cloud Run Deployment"
    echo "=========================================="
    echo ""
    
    check_prerequisites
    
    # Check for required secrets
    if [ -z "$CARTPILOT_API_KEY" ]; then
        warning "CARTPILOT_API_KEY not set. Using default (not recommended for production)"
        CARTPILOT_API_KEY="dev-api-key-change-in-production"
    fi
    
    if [ -z "$WEBHOOK_SECRET" ]; then
        warning "WEBHOOK_SECRET not set. Using default (not recommended for production)"
        WEBHOOK_SECRET="dev-webhook-secret-change-in-production"
    fi
    
    if [ "$build_only" = true ]; then
        build_all_images
    elif [ "$deploy_only" = true ]; then
        deploy_all_services
        show_summary
    else
        build_all_images
        echo ""
        deploy_all_services
        show_summary
    fi
}

# Run main function
main "$@"

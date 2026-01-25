#!/bin/bash
# GCP Setup Script for CartPilot
# This script sets up a GCP project and Artifact Registry for CartPilot deployment

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration variables (can be overridden via environment)
PROJECT_ID="${GCP_PROJECT_ID:-cartpilot-$(date +%s)}"
REGION="${GCP_REGION:-us-central1}"
ARTIFACT_REGISTRY_REPO="${ARTIFACT_REGISTRY_REPO:-cartpilot-docker}"
BILLING_ACCOUNT="${GCP_BILLING_ACCOUNT:-}"

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

# Check if gcloud is installed
check_gcloud() {
    if ! command -v gcloud &> /dev/null; then
        error "gcloud CLI is not installed. Please install it from: https://cloud.google.com/sdk/docs/install"
        exit 1
    fi
    info "gcloud CLI found: $(gcloud --version | head -n1)"
}

# Check if user is authenticated
check_auth() {
    if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q .; then
        warning "No active gcloud authentication found. Please run: gcloud auth login"
        read -p "Do you want to authenticate now? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            gcloud auth login
        else
            error "Authentication required to continue"
            exit 1
        fi
    fi
    success "Authenticated as: $(gcloud auth list --filter=status:ACTIVE --format='value(account)')"
}

# Create or use existing GCP project
setup_project() {
    info "Setting up GCP project: $PROJECT_ID"
    
    # Check if project exists
    if gcloud projects describe "$PROJECT_ID" &>/dev/null; then
        success "Project $PROJECT_ID already exists"
    else
        info "Creating new project: $PROJECT_ID"
        gcloud projects create "$PROJECT_ID" --name="CartPilot" || {
            error "Failed to create project. It may already exist or you may not have permissions."
            exit 1
        }
        success "Project $PROJECT_ID created"
    fi
    
    # Set as current project
    gcloud config set project "$PROJECT_ID"
    success "Set project to: $PROJECT_ID"
    
    # Link billing account if provided
    if [[ -n "$BILLING_ACCOUNT" ]]; then
        info "Linking billing account: $BILLING_ACCOUNT"
        gcloud billing projects link "$PROJECT_ID" --billing-account="$BILLING_ACCOUNT" || {
            warning "Failed to link billing account. You may need to do this manually."
        }
    else
        warning "No billing account specified. Some services may require billing to be enabled."
        warning "Set GCP_BILLING_ACCOUNT environment variable to link billing automatically."
    fi
}

# Enable required APIs
enable_apis() {
    info "Enabling required GCP APIs..."
    
    local apis=(
        "run.googleapis.com"              # Cloud Run API
        "sqladmin.googleapis.com"         # Cloud SQL Admin API
        "artifactregistry.googleapis.com" # Artifact Registry API
        "secretmanager.googleapis.com"    # Secret Manager API
        "compute.googleapis.com"          # Compute Engine API (for VPC)
        "servicenetworking.googleapis.com" # Service Networking API (for VPC)
    )
    
    for api in "${apis[@]}"; do
        info "Enabling $api..."
        gcloud services enable "$api" --project="$PROJECT_ID" || {
            warning "Failed to enable $api. It may already be enabled or billing may not be linked."
        }
    done
    
    success "APIs enabled"
}

# Create Artifact Registry repository
setup_artifact_registry() {
    info "Setting up Artifact Registry repository: $ARTIFACT_REGISTRY_REPO"
    
    # Check if repository already exists
    if gcloud artifacts repositories describe "$ARTIFACT_REGISTRY_REPO" \
        --location="$REGION" \
        --repository-format=docker \
        --project="$PROJECT_ID" &>/dev/null; then
        success "Repository $ARTIFACT_REGISTRY_REPO already exists"
    else
        info "Creating Docker repository in Artifact Registry..."
        gcloud artifacts repositories create "$ARTIFACT_REGISTRY_REPO" \
            --repository-format=docker \
            --location="$REGION" \
            --description="CartPilot Docker images" \
            --project="$PROJECT_ID" || {
            error "Failed to create Artifact Registry repository"
            exit 1
        }
        success "Repository $ARTIFACT_REGISTRY_REPO created"
    fi
    
    # Configure Docker authentication
    info "Configuring Docker authentication for Artifact Registry..."
    gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet || {
        error "Failed to configure Docker authentication"
        exit 1
    }
    success "Docker authentication configured"
    
    # Display repository URL
    local repo_url="${REGION}-docker.pkg.dev/${PROJECT_ID}/${ARTIFACT_REGISTRY_REPO}"
    success "Artifact Registry repository URL: $repo_url"
    echo ""
    info "You can push images using:"
    echo "  docker tag <image> $repo_url/<image-name>:<tag>"
    echo "  docker push $repo_url/<image-name>:<tag>"
}

# Create service account for Cloud Run (optional, for later use)
create_service_account() {
    info "Creating service account for Cloud Run deployments..."
    
    local sa_name="cartpilot-cloudrun"
    local sa_email="${sa_name}@${PROJECT_ID}.iam.gserviceaccount.com"
    
    if gcloud iam service-accounts describe "$sa_email" --project="$PROJECT_ID" &>/dev/null; then
        success "Service account $sa_email already exists"
    else
        gcloud iam service-accounts create "$sa_name" \
            --display-name="CartPilot Cloud Run Service Account" \
            --project="$PROJECT_ID" || {
            warning "Failed to create service account. You may not have permissions."
            return
        }
        success "Service account created: $sa_email"
    fi
    
    # Grant necessary permissions
    info "Granting permissions to service account..."
    gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --member="serviceAccount:${sa_email}" \
        --role="roles/cloudsql.client" \
        --condition=None &>/dev/null || true
    
    gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --member="serviceAccount:${sa_email}" \
        --role="roles/secretmanager.secretAccessor" \
        --condition=None &>/dev/null || true
    
    success "Service account configured"
}

# Save configuration to file
save_config() {
    local config_file="deploy/gcp/config.env"
    info "Saving configuration to $config_file"
    
    mkdir -p "$(dirname "$config_file")"
    
    cat > "$config_file" <<EOF
# GCP Configuration for CartPilot
# Generated by setup.sh on $(date)

export GCP_PROJECT_ID="$PROJECT_ID"
export GCP_REGION="$REGION"
export ARTIFACT_REGISTRY_REPO="$ARTIFACT_REGISTRY_REPO"
export ARTIFACT_REGISTRY_URL="${REGION}-docker.pkg.dev/${PROJECT_ID}/${ARTIFACT_REGISTRY_REPO}"
export GCP_SERVICE_ACCOUNT="cartpilot-cloudrun@${PROJECT_ID}.iam.gserviceaccount.com"
EOF
    
    success "Configuration saved to $config_file"
    info "To use this configuration in other scripts, run: source $config_file"
}

# Main execution
main() {
    echo ""
    echo "=========================================="
    echo "  CartPilot GCP Setup Script"
    echo "=========================================="
    echo ""
    
    check_gcloud
    check_auth
    
    echo ""
    info "Configuration:"
    echo "  Project ID: $PROJECT_ID"
    echo "  Region: $REGION"
    echo "  Artifact Registry Repo: $ARTIFACT_REGISTRY_REPO"
    echo ""
    
    read -p "Continue with setup? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        info "Setup cancelled"
        exit 0
    fi
    
    setup_project
    enable_apis
    setup_artifact_registry
    create_service_account
    save_config
    
    echo ""
    echo "=========================================="
    success "GCP setup completed successfully!"
    echo "=========================================="
    echo ""
    info "Next steps:"
    echo "  1. Source the configuration: source deploy/gcp/config.env"
    echo "  2. Build and push Docker images to Artifact Registry"
    echo "  3. Deploy services to Cloud Run using deploy.sh"
    echo ""
}

# Run main function
main "$@"

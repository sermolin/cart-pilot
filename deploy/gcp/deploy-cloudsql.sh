#!/bin/bash
# Cloud SQL Deployment Script for CartPilot
# Creates Cloud SQL PostgreSQL instance with private IP

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Load configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/config.env" ]; then
    source "$SCRIPT_DIR/config.env"
else
    echo -e "${RED}Error: config.env not found. Please run setup.sh first.${NC}"
    exit 1
fi

# Cloud SQL configuration
CLOUDSQL_INSTANCE_NAME="${CLOUDSQL_INSTANCE_NAME:-cartpilot-db}"
CLOUDSQL_DATABASE_NAME="${CLOUDSQL_DATABASE_NAME:-cartpilot}"
CLOUDSQL_USER="${CLOUDSQL_USER:-cartpilot}"
CLOUDSQL_PASSWORD="${CLOUDSQL_PASSWORD:-}"
CLOUDSQL_TIER="${CLOUDSQL_TIER:-db-f1-micro}"  # Minimal tier for demo/testing
CLOUDSQL_VERSION="${CLOUDSQL_VERSION:-POSTGRES_16}"

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

# Check if gcloud is installed and authenticated
check_prerequisites() {
    if ! command -v gcloud &> /dev/null; then
        error "gcloud CLI is not installed"
        exit 1
    fi
    
    if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q .; then
        error "Not authenticated. Please run: gcloud auth login"
        exit 1
    fi
    
    gcloud config set project "$GCP_PROJECT_ID" > /dev/null 2>&1
    success "Using project: $GCP_PROJECT_ID"
}

# Generate random password if not provided
generate_password() {
    if [ -z "$CLOUDSQL_PASSWORD" ]; then
        CLOUDSQL_PASSWORD=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-25)
        info "Generated password for database user"
    fi
}

# Create VPC connector for private IP (if needed)
setup_vpc_connector() {
    local connector_name="cartpilot-vpc-connector"
    
    info "Checking VPC connector..."
    
    if gcloud compute networks vpc-access connectors describe "$connector_name" \
        --region="$GCP_REGION" \
        --project="$GCP_PROJECT_ID" &>/dev/null; then
        success "VPC connector already exists"
    else
        info "Creating VPC connector for private IP access..."
        
        # Enable VPC Access API
        gcloud services enable vpcaccess.googleapis.com --project="$GCP_PROJECT_ID" || true
        
        # Create VPC connector
        gcloud compute networks vpc-access connectors create "$connector_name" \
            --region="$GCP_REGION" \
            --network=default \
            --range=10.8.0.0/28 \
            --min-instances=2 \
            --max-instances=3 \
            --machine-type=e2-micro \
            --project="$GCP_PROJECT_ID" || {
            warning "Failed to create VPC connector. You may need to enable it manually."
            return
        }
        
        success "VPC connector created"
    fi
    
    export VPC_CONNECTOR_NAME="$connector_name"
}

# Create Cloud SQL instance
create_cloudsql_instance() {
    info "Checking Cloud SQL instance: $CLOUDSQL_INSTANCE_NAME"
    
    if gcloud sql instances describe "$CLOUDSQL_INSTANCE_NAME" \
        --project="$GCP_PROJECT_ID" &>/dev/null; then
        success "Cloud SQL instance already exists"
        return 0
    fi
    
    info "Creating Cloud SQL PostgreSQL instance..."
    info "  Instance name: $CLOUDSQL_INSTANCE_NAME"
    info "  Tier: $CLOUDSQL_TIER"
    info "  Region: $GCP_REGION"
    info "  Version: $CLOUDSQL_VERSION"
    
    # Create instance with private IP
    gcloud sql instances create "$CLOUDSQL_INSTANCE_NAME" \
        --database-version="$CLOUDSQL_VERSION" \
        --tier="$CLOUDSQL_TIER" \
        --region="$GCP_REGION" \
        --network=default \
        --no-assign-ip \
        --project="$GCP_PROJECT_ID" || {
        error "Failed to create Cloud SQL instance"
        exit 1
    }
    
    success "Cloud SQL instance created"
    
    # Wait for instance to be ready
    info "Waiting for instance to be ready..."
    while ! gcloud sql instances describe "$CLOUDSQL_INSTANCE_NAME" \
        --project="$GCP_PROJECT_ID" \
        --format="value(state)" | grep -q "RUNNABLE"; do
        sleep 5
    done
    
    success "Instance is ready"
}

# Configure private IP
configure_private_ip() {
    info "Configuring private IP access..."
    
    # Allocate IP range for private service connection
    gcloud compute addresses create google-managed-services-default \
        --global \
        --purpose=VPC_PEERING \
        --prefix-length=16 \
        --network=default \
        --project="$GCP_PROJECT_ID" 2>/dev/null || true
    
    # Create private connection
    gcloud services vpc-peerings connect \
        --service=servicenetworking.googleapis.com \
        --ranges=google-managed-services-default \
        --network=default \
        --project="$GCP_PROJECT_ID" 2>/dev/null || true
    
    # Update instance to use private IP
    gcloud sql instances patch "$CLOUDSQL_INSTANCE_NAME" \
        --network=default \
        --no-assign-ip \
        --project="$GCP_PROJECT_ID" || {
        warning "Private IP configuration may need manual setup"
    }
    
    success "Private IP configured"
}

# Create database
create_database() {
    info "Creating database: $CLOUDSQL_DATABASE_NAME"
    
    if gcloud sql databases describe "$CLOUDSQL_DATABASE_NAME" \
        --instance="$CLOUDSQL_INSTANCE_NAME" \
        --project="$GCP_PROJECT_ID" &>/dev/null; then
        success "Database already exists"
    else
        gcloud sql databases create "$CLOUDSQL_DATABASE_NAME" \
            --instance="$CLOUDSQL_INSTANCE_NAME" \
            --project="$GCP_PROJECT_ID" || {
            error "Failed to create database"
            exit 1
        }
        success "Database created"
    fi
}

# Create database user
create_database_user() {
    info "Creating database user: $CLOUDSQL_USER"
    
    # Check if user exists
    if gcloud sql users list \
        --instance="$CLOUDSQL_INSTANCE_NAME" \
        --project="$GCP_PROJECT_ID" \
        --format="value(name)" | grep -q "^$CLOUDSQL_USER$"; then
        warning "User already exists. Updating password..."
        gcloud sql users set-password "$CLOUDSQL_USER" \
            --instance="$CLOUDSQL_INSTANCE_NAME" \
            --password="$CLOUDSQL_PASSWORD" \
            --project="$GCP_PROJECT_ID" || {
            error "Failed to update user password"
            exit 1
        }
        success "User password updated"
    else
        gcloud sql users create "$CLOUDSQL_USER" \
            --instance="$CLOUDSQL_INSTANCE_NAME" \
            --password="$CLOUDSQL_PASSWORD" \
            --project="$GCP_PROJECT_ID" || {
            error "Failed to create user"
            exit 1
        }
        success "User created"
    fi
}

# Get connection name
get_connection_name() {
    local connection_name=$(gcloud sql instances describe "$CLOUDSQL_INSTANCE_NAME" \
        --project="$GCP_PROJECT_ID" \
        --format="value(connectionName)")
    
    export CLOUDSQL_CONNECTION_NAME="$connection_name"
    success "Connection name: $connection_name"
}

# Save Cloud SQL configuration
save_cloudsql_config() {
    local config_file="$SCRIPT_DIR/config.env"
    
    info "Saving Cloud SQL configuration..."
    
    # Append to config.env
    cat >> "$config_file" <<EOF

# Cloud SQL Configuration
export CLOUDSQL_INSTANCE_NAME="$CLOUDSQL_INSTANCE_NAME"
export CLOUDSQL_DATABASE_NAME="$CLOUDSQL_DATABASE_NAME"
export CLOUDSQL_USER="$CLOUDSQL_USER"
export CLOUDSQL_CONNECTION_NAME="$CLOUDSQL_CONNECTION_NAME"
export CLOUDSQL_DATABASE_URL="postgresql+asyncpg://${CLOUDSQL_USER}:${CLOUDSQL_PASSWORD}@/${CLOUDSQL_DATABASE_NAME}?host=/cloudsql/${CLOUDSQL_CONNECTION_NAME}"
EOF
    
    success "Configuration saved to $config_file"
    warning "Database password saved in config.env. Keep this file secure!"
}

# Main execution
main() {
    echo ""
    echo "=========================================="
    echo "  CartPilot Cloud SQL Deployment"
    echo "=========================================="
    echo ""
    
    check_prerequisites
    generate_password
    
    echo ""
    info "Configuration:"
    echo "  Instance: $CLOUDSQL_INSTANCE_NAME"
    echo "  Database: $CLOUDSQL_DATABASE_NAME"
    echo "  User: $CLOUDSQL_USER"
    echo "  Tier: $CLOUDSQL_TIER"
    echo ""
    
    read -p "Continue with Cloud SQL setup? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        info "Setup cancelled"
        exit 0
    fi
    
    setup_vpc_connector
    create_cloudsql_instance
    configure_private_ip
    create_database
    create_database_user
    get_connection_name
    save_cloudsql_config
    
    echo ""
    echo "=========================================="
    success "Cloud SQL setup completed!"
    echo "=========================================="
    echo ""
    info "Next steps:"
    echo "  1. Build and push Docker images to Artifact Registry"
    echo "  2. Deploy services to Cloud Run using deploy.sh"
    echo ""
    info "Connection details saved in: $SCRIPT_DIR/config.env"
    echo ""
}

# Run main function
main "$@"

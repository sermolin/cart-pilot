# GCP Deployment Scripts

This directory contains scripts for deploying CartPilot to Google Cloud Platform.

## Prerequisites

1. **Google Cloud SDK (gcloud CLI)**
   - Install from: https://cloud.google.com/sdk/docs/install
   - Authenticate: `gcloud auth login`

2. **GCP Project**
   - You can create a new project or use an existing one
   - Billing account should be linked (required for Cloud SQL and some APIs)

3. **Docker**
   - Required for building and pushing images to Artifact Registry

## Setup Script (`setup.sh`)

The setup script initializes your GCP project and Artifact Registry.

### Usage

```bash
# Basic usage (creates new project)
./deploy/gcp/setup.sh

# With custom project ID
GCP_PROJECT_ID=my-cartpilot-project ./deploy/gcp/setup.sh

# With billing account
GCP_PROJECT_ID=my-project GCP_BILLING_ACCOUNT=XXXXXX-XXXXXX-XXXXXX ./deploy/gcp/setup.sh

# With custom region
GCP_REGION=europe-west1 ./deploy/gcp/setup.sh
```

### What it does

1. **Checks prerequisites**
   - Verifies gcloud CLI is installed
   - Checks authentication status

2. **Creates/uses GCP project**
   - Creates a new project or uses existing one
   - Sets it as the active project
   - Links billing account (if provided)

3. **Enables required APIs**
   - Cloud Run API
   - Cloud SQL Admin API
   - Artifact Registry API
   - Secret Manager API
   - Compute Engine API
   - Service Networking API

4. **Sets up Artifact Registry**
   - Creates Docker repository
   - Configures Docker authentication
   - Displays repository URL

5. **Creates service account**
   - Creates service account for Cloud Run
   - Grants necessary permissions

6. **Saves configuration**
   - Creates `config.env` with project settings
   - Can be sourced in other scripts

### Configuration File

After running setup, a `config.env` file is created with:

```bash
export GCP_PROJECT_ID="cartpilot-xxxxx"
export GCP_REGION="us-central1"
export ARTIFACT_REGISTRY_REPO="cartpilot-docker"
export ARTIFACT_REGISTRY_URL="us-central1-docker.pkg.dev/cartpilot-xxxxx/cartpilot-docker"
export GCP_SERVICE_ACCOUNT="cartpilot-cloudrun@cartpilot-xxxxx.iam.gserviceaccount.com"
```

Source it in other scripts:

```bash
source deploy/gcp/config.env
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GCP_PROJECT_ID` | GCP project ID | `cartpilot-<timestamp>` |
| `GCP_REGION` | GCP region | `us-central1` |
| `ARTIFACT_REGISTRY_REPO` | Artifact Registry repository name | `cartpilot-docker` |
| `GCP_BILLING_ACCOUNT` | Billing account ID (optional) | (none) |

## Troubleshooting

### "Permission denied" errors

Make sure you have the necessary IAM permissions:
- Project Creator (if creating new project)
- Service Usage Admin (to enable APIs)
- Artifact Registry Admin (to create repositories)

### Billing not linked

Some APIs require billing to be enabled. Link a billing account:
```bash
gcloud billing projects link PROJECT_ID --billing-account=BILLING_ACCOUNT_ID
```

### Docker authentication fails

Try re-authenticating:
```bash
gcloud auth configure-docker REGION-docker.pkg.dev
```

## Cloud SQL Deployment (`deploy-cloudsql.sh`)

Creates and configures a Cloud SQL PostgreSQL instance with private IP.

### Usage

```bash
# Run after setup.sh
./deploy/gcp/deploy-cloudsql.sh
```

### What it does

1. **Creates VPC connector** for private IP access
2. **Creates Cloud SQL instance** with PostgreSQL 16
3. **Configures private IP** for secure Cloud Run connection
4. **Creates database** (`cartpilot`)
5. **Creates database user** with generated password
6. **Saves connection details** to `config.env`

### Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `CLOUDSQL_INSTANCE_NAME` | Instance name | `cartpilot-db` |
| `CLOUDSQL_DATABASE_NAME` | Database name | `cartpilot` |
| `CLOUDSQL_USER` | Database user | `cartpilot` |
| `CLOUDSQL_PASSWORD` | Database password | (auto-generated) |
| `CLOUDSQL_TIER` | Instance tier | `db-f1-micro` |

### Cost

- `db-f1-micro`: ~$7-10/month (minimal tier for demo/testing)
- `db-f1-small`: ~$15-20/month (recommended for production)

## Cloud Run Deployment (`deploy.sh`)

Builds Docker images, pushes to Artifact Registry, and deploys all services to Cloud Run.

### Usage

```bash
# Build images and deploy all services
./deploy/gcp/deploy.sh

# Build images only (don't deploy)
./deploy/gcp/deploy.sh --build-only

# Deploy only (assumes images already built)
./deploy/gcp/deploy.sh --deploy-only
```

### What it does

1. **Builds Docker images** for all services
2. **Pushes images** to Artifact Registry
3. **Deploys services** in correct order:
   - `merchant-a` and `merchant-b` (no dependencies)
   - `cartpilot-api` (depends on Cloud SQL and merchants)
   - `cartpilot-mcp` (depends on API)

### Deployment Order

The script automatically handles dependencies:

1. **Merchants** are deployed first (no dependencies)
2. **CartPilot API** is deployed with Cloud SQL connection and merchant URLs
3. **MCP Server** is deployed with API URL
4. **Webhook URLs** are updated after API deployment

### Environment Variables

Required (set before deployment):

```bash
export CARTPILOT_API_KEY="your-secure-api-key"
export WEBHOOK_SECRET="your-webhook-secret"
```

Or set in `config.env`:

```bash
export CARTPILOT_API_KEY="your-secure-api-key"
export WEBHOOK_SECRET="your-webhook-secret"
source deploy/gcp/config.env
./deploy/gcp/deploy.sh
```

### Service Configuration

| Service | Memory | CPU | Min Instances | Max Instances |
|---------|--------|-----|--------------|---------------|
| merchant-a | 512Mi | 1 | 0 | 10 |
| merchant-b | 512Mi | 1 | 0 | 10 |
| cartpilot-api | 1Gi | 1 | 0 | 10 |
| cartpilot-mcp | 512Mi | 1 | 0 | 10 |

### Service URLs

After deployment, services will be available at:

- `https://merchant-a-xxxx.run.app`
- `https://merchant-b-xxxx.run.app`
- `https://cartpilot-api-xxxx.run.app`
- `https://cartpilot-mcp-xxxx.run.app`

MCP SSE endpoint: `https://cartpilot-mcp-xxxx.run.app/sse`

## Complete Deployment Workflow

### Step 1: Initial Setup

```bash
# Set up GCP project and Artifact Registry
./deploy/gcp/setup.sh
```

### Step 2: Deploy Cloud SQL

```bash
# Create Cloud SQL instance
./deploy/gcp/deploy-cloudsql.sh
```

### Step 3: Set Secrets

```bash
# Edit config.env or set environment variables
export CARTPILOT_API_KEY="your-secure-api-key"
export WEBHOOK_SECRET="your-webhook-secret"
```

### Step 4: Deploy to Cloud Run

```bash
# Build and deploy all services
./deploy/gcp/deploy.sh
```

### Step 5: Verify Deployment

```bash
# Test health endpoints
curl https://cartpilot-api-xxxx.run.app/health
curl https://merchant-a-xxxx.run.app/health
curl https://merchant-b-xxxx.run.app/health
curl https://cartpilot-mcp-xxxx.run.app/health
```

## Troubleshooting

### Cloud SQL connection issues

If Cloud Run can't connect to Cloud SQL:

1. Check VPC connector is created:
   ```bash
   gcloud compute networks vpc-access connectors list --region=$GCP_REGION
   ```

2. Verify Cloud SQL instance has private IP:
   ```bash
   gcloud sql instances describe $CLOUDSQL_INSTANCE_NAME
   ```

3. Check service account has Cloud SQL Client role:
   ```bash
   gcloud projects get-iam-policy $GCP_PROJECT_ID \
     --flatten="bindings[].members" \
     --filter="bindings.members:serviceAccount:$GCP_SERVICE_ACCOUNT"
   ```

### Image build failures

If Docker build fails:

1. Check Docker is running: `docker info`
2. Verify Docker authentication: `gcloud auth configure-docker $REGION-docker.pkg.dev`
3. Check Artifact Registry permissions

### Deployment failures

If Cloud Run deployment fails:

1. Check logs: `gcloud run services logs read SERVICE_NAME --region=$GCP_REGION`
2. Verify environment variables are set correctly
3. Check service account permissions
4. Verify Cloud SQL connection string format

## Cost Estimation

For demo/testing setup:

- **Cloud Run**: ~$0-5/month (free tier covers low traffic)
- **Cloud SQL** (db-f1-micro): ~$7-10/month
- **Artifact Registry**: ~$0.10/GB/month
- **VPC Connector**: ~$0/month (free tier)

**Total: ~$10-20/month** for demo/testing

For production:

- **Cloud Run**: ~$20-50/month (depending on traffic)
- **Cloud SQL** (db-f1-small): ~$15-20/month
- **Artifact Registry**: ~$1-2/month
- **VPC Connector**: ~$0/month

**Total: ~$40-75/month** for production

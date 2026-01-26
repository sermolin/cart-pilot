# Step-by-Step Guide for Deploying CartPilot to GCP

This practical guide will help you deploy CartPilot to Google Cloud Platform.

## Prerequisites

1. **Google Cloud SDK (gcloud CLI)**
   ```bash
   # Check installation
   gcloud --version
   
   # If not installed:
   # macOS: brew install google-cloud-sdk
   # Linux: https://cloud.google.com/sdk/docs/install
   ```

2. **GCP Authentication**
   ```bash
   gcloud auth login
   gcloud auth application-default login
   ```

3. **Docker**
   ```bash
   docker --version
   # Make sure Docker is running
   ```

4. **Billing Account** (for Cloud SQL)
   - You must have an active billing account in GCP
   - Cloud SQL requires billing to be enabled

## Step 1: GCP Project Setup

### 1.1. Run the Setup Script

```bash
cd cart-pilot

# Basic run (creates new project)
./deploy/gcp/setup.sh

# Or with existing project
GCP_PROJECT_ID=your-existing-project ./deploy/gcp/setup.sh

# With billing account
GCP_PROJECT_ID=your-project \
GCP_BILLING_ACCOUNT=XXXXXX-XXXXXX-XXXXXX \
./deploy/gcp/setup.sh
```

### 1.2. What Happens

The script:
- ✅ Checks gcloud installation
- ✅ Creates or uses GCP project
- ✅ Enables required APIs
- ✅ Creates Artifact Registry repository
- ✅ Configures Docker authentication
- ✅ Creates service account
- ✅ Saves configuration to `deploy/gcp/config.env`

### 1.3. Verify Result

After the script completes, verify:

```bash
# Load configuration
source deploy/gcp/config.env

# Check variables
echo "Project: $GCP_PROJECT_ID"
echo "Region: $GCP_REGION"
echo "Artifact Registry: $ARTIFACT_REGISTRY_URL"
```

## Step 2: Deploy Cloud SQL

### 2.1. Run the Database Deployment Script

```bash
# Make sure config.env is loaded
source deploy/gcp/config.env

# Run Cloud SQL deployment
./deploy/gcp/deploy-cloudsql.sh
```

### 2.2. What Happens

The script:
- ✅ Creates VPC connector for private IP
- ✅ Creates Cloud SQL PostgreSQL instance
- ✅ Configures private IP
- ✅ Creates `cartpilot` database
- ✅ Creates user with auto-generated password
- ✅ Saves connection string to `config.env`

### 2.3. Verify Result

```bash
# Check that instance is created
gcloud sql instances list --project=$GCP_PROJECT_ID

# Check connection string in config.env
source deploy/gcp/config.env
echo "Connection: $CLOUDSQL_CONNECTION_NAME"
```

**Important:** This may take 5-10 minutes. Wait for completion.

## Step 3: Prepare Secrets

### 3.1. Create Secure Keys

```bash
# Generate API key
export CARTPILOT_API_KEY=$(openssl rand -hex 32)

# Generate webhook secret
export WEBHOOK_SECRET=$(openssl rand -hex 32)

# Or use your own values
export CARTPILOT_API_KEY="your-secure-api-key-here"
export WEBHOOK_SECRET="your-webhook-secret-here"
```

### 3.2. Save to config.env (optional)

```bash
# Add to config.env
cat >> deploy/gcp/config.env <<EOF
export CARTPILOT_API_KEY="$CARTPILOT_API_KEY"
export WEBHOOK_SECRET="$WEBHOOK_SECRET"
EOF
```

## Step 4: Deploy Services to Cloud Run

### 4.1. Run the Deployment Script

```bash
# Make sure all variables are set
source deploy/gcp/config.env

# Check that secrets are set
echo "API Key: ${CARTPILOT_API_KEY:0:10}..."
echo "Webhook Secret: ${WEBHOOK_SECRET:0:10}..."

# Run deployment
./deploy/gcp/deploy.sh
```

### 4.2. What Happens

The script automatically:
1. **Builds Docker images** for all services
2. **Pushes images** to Artifact Registry
3. **Deploys services** in correct order:
   - `merchant-a` and `merchant-b` (no dependencies)
   - `cartpilot-api` (connects to Cloud SQL and merchants)
   - `cartpilot-mcp` (connects to API)
4. **Updates webhook URLs** after API deployment

### 4.3. Execution Time

- Building images: ~5-10 minutes (depends on internet speed)
- Deploying services: ~2-3 minutes each
- **Total time: ~15-20 minutes**

## Step 5: Verify Deployment

### 5.1. Get Service URLs

```bash
source deploy/gcp/config.env

# CartPilot API
API_URL=$(gcloud run services describe cartpilot-api \
  --region=$GCP_REGION \
  --project=$GCP_PROJECT_ID \
  --format="value(status.url)")

echo "CartPilot API: $API_URL"

# MCP Server
MCP_URL=$(gcloud run services describe cartpilot-mcp \
  --region=$GCP_REGION \
  --project=$GCP_PROJECT_ID \
  --format="value(status.url)")

echo "MCP Server: $MCP_URL"
```

### 5.2. Check Health Endpoints

```bash
# Check API
curl "$API_URL/health"

# Check MCP
curl "$MCP_URL/health"
```

### 5.3. Test API

```bash
# Create intent
curl -X POST "$API_URL/intents" \
  -H "Authorization: Bearer $CARTPILOT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "test product", "session_id": "test"}'
```

## Step 6: Configure Integrations

### 6.1. MCP Server (Claude, Cline)

Use MCP SSE endpoint:
```
https://cartpilot-mcp-xxxx.run.app/sse
```

### 6.2. ChatGPT Actions

1. Update `docs/openapi.yaml`:
   ```yaml
   servers:
     - url: https://cartpilot-api-xxxx.run.app
   ```

2. Import in ChatGPT Custom GPT
3. Configure authentication with your API key

### 6.3. Gemini Function Calling

```bash
export GEMINI_API_KEY="your-gemini-key"
export CARTPILOT_API_URL="$API_URL"
export CARTPILOT_API_KEY="$CARTPILOT_API_KEY"

python integrations/example_chat.py
```

## Troubleshooting

### Problem: "Permission denied"

```bash
# Check access permissions
gcloud projects get-iam-policy $GCP_PROJECT_ID \
  --flatten="bindings[].members" \
  --filter="bindings.members:user:$(gcloud config get-value account)"

# Required roles:
# - Cloud Run Admin
# - Cloud SQL Admin
# - Artifact Registry Admin
# - Service Account User
```

### Problem: Cloud SQL not connecting

```bash
# Check VPC connector
gcloud compute networks vpc-access connectors list \
  --region=$GCP_REGION

# Check private IP
gcloud sql instances describe $CLOUDSQL_INSTANCE_NAME \
  --format="value(ipAddresses[0].ipAddress)"
```

### Problem: Images not building

```bash
# Check Docker authentication
gcloud auth configure-docker $REGION-docker.pkg.dev

# Check Artifact Registry permissions
gcloud artifacts repositories get-iam-policy $ARTIFACT_REGISTRY_REPO \
  --location=$GCP_REGION
```

### Problem: Services not starting

```bash
# Check logs
gcloud run services logs read cartpilot-api \
  --region=$GCP_REGION \
  --limit=50

# Check environment variables
gcloud run services describe cartpilot-api \
  --region=$GCP_REGION \
  --format="value(spec.template.spec.containers[0].env)"
```

## Tear Down Deployment

If you need to delete everything:

```bash
source deploy/gcp/config.env

# Delete Cloud Run services
gcloud run services delete cartpilot-api --region=$GCP_REGION
gcloud run services delete cartpilot-mcp --region=$GCP_REGION
gcloud run services delete merchant-a --region=$GCP_REGION
gcloud run services delete merchant-b --region=$GCP_REGION

# Delete Cloud SQL (caution!)
gcloud sql instances delete $CLOUDSQL_INSTANCE_NAME

# Delete Artifact Registry
gcloud artifacts repositories delete $ARTIFACT_REGISTRY_REPO \
  --location=$GCP_REGION

# Delete VPC connector
gcloud compute networks vpc-access connectors delete cartpilot-vpc-connector \
  --region=$GCP_REGION
```

## Next Steps

1. ✅ Set up monitoring and alerts
2. ✅ Configure Cloud SQL backups
3. ✅ Set up custom domain (optional)
4. ✅ Configure CI/CD for automatic deployment
5. ✅ Set up Secret Manager for secrets

## Useful Commands

```bash
# View all services
gcloud run services list --region=$GCP_REGION

# View logs in real-time
gcloud run services logs tail cartpilot-api --region=$GCP_REGION

# Update environment variables
gcloud run services update cartpilot-api \
  --region=$GCP_REGION \
  --update-env-vars="LOG_LEVEL=DEBUG"

# Scale services
gcloud run services update cartpilot-api \
  --region=$GCP_REGION \
  --min-instances=1 \
  --max-instances=10
```

## Support

If you encounter issues:
1. Check service logs
2. Review documentation in `deploy/gcp/README.md`
3. Ensure all prerequisites are met

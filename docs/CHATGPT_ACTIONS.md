# ChatGPT Actions Integration

This guide explains how to integrate CartPilot API with ChatGPT Actions using the OpenAPI specification.

## Overview

ChatGPT Actions allow you to connect ChatGPT to external APIs. CartPilot provides a complete OpenAPI 3.0 specification that enables ChatGPT to:

- Create purchase intents from natural language
- Search for products across merchants
- Manage checkout approval workflows
- Track order status

## Prerequisites

1. **ChatGPT Plus or Enterprise** account
2. **CartPilot API deployed** and accessible (Cloud Run or local)
3. **API Key** for authentication

## Setup Steps

### 1. Deploy CartPilot API

Deploy CartPilot API to Cloud Run or make it accessible:

```bash
# After deployment, get the API URL
gcloud run services describe cartpilot-api \
  --region=us-central1 \
  --format="value(status.url)"
```

### 2. Update OpenAPI Specification

Edit `docs/openapi.yaml` and update the server URL:

```yaml
servers:
  - url: https://cartpilot-api-xxxx.run.app
    description: Production server
```

Replace `xxxx` with your actual Cloud Run service identifier.

### 3. Create Custom GPT

1. Go to [ChatGPT Custom GPTs](https://chat.openai.com/gpts)
2. Click **"Create"** or **"Edit"** a GPT
3. Go to **"Configure"** tab
4. Scroll to **"Actions"** section
5. Click **"Create new action"**

### 4. Import OpenAPI Schema

1. In the Actions configuration:
   - **Schema**: Select "Import from URL" or paste the OpenAPI YAML content
   - **URL**: `https://your-domain.com/docs/openapi.yaml` (or paste YAML directly)
2. **Authentication**:
   - Type: `API Key`
   - Auth Type: `Bearer Token`
   - API Key: Your CartPilot API key
   - Add to: `Header` (as `Authorization: Bearer {api_key}`)

### 5. Configure GPT Instructions

Add instructions to help ChatGPT understand CartPilot:

```
You are a shopping assistant powered by CartPilot. You help users find and purchase products.

Workflow:
1. When user wants to buy something, create an intent using their natural language query
2. Get offers from merchants for that intent
3. Show the user available products and prices
4. When user selects a product, create a checkout
5. Get a quote from the merchant
6. Request approval before purchase
7. After approval, confirm the purchase
8. Track order status

Always explain what you're doing at each step. Never make purchases without explicit user approval.
```

## Example Usage

### User: "I need wireless headphones under $100"

**ChatGPT will:**
1. Call `POST /intents` with query: "wireless headphones under $100"
2. Call `GET /intents/{id}/offers` to get product offers
3. Display available headphones with prices
4. Wait for user selection

### User: "Buy the Sony WH-1000XM4"

**ChatGPT will:**
1. Call `POST /checkouts` with the selected offer
2. Call `POST /checkouts/{id}/quote` to get pricing
3. Call `POST /checkouts/{id}/request-approval` to freeze receipt
4. Show approval request with total price
5. Wait for user approval

### User: "Approve the purchase"

**ChatGPT will:**
1. Call `POST /checkouts/{id}/approve`
2. Call `POST /checkouts/{id}/confirm` to execute purchase
3. Show order confirmation with order ID
4. Offer to track order status

## API Endpoints Available to ChatGPT

### Intents
- `createIntent` - Create purchase intent from natural language
- `getIntent` - Get intent details
- `getIntentOffers` - Get offers from merchants

### Offers
- `getOffer` - Get detailed offer information

### Checkouts
- `createCheckout` - Create checkout from offer
- `getCheckout` - Get checkout details
- `quoteCheckout` - Get quote from merchant
- `requestApproval` - Request approval and freeze receipt
- `approveCheckout` - Approve the purchase
- `confirmCheckout` - Execute the purchase

### Orders
- `listOrders` - List orders with filtering
- `getOrder` - Get order details and status
- `cancelOrder` - Cancel an order
- `refundOrder` - Refund an order

## Testing

### Test Locally

1. Start CartPilot API locally:
   ```bash
   docker compose up cartpilot-api
   ```

2. Update OpenAPI spec to use `http://localhost:8000`

3. Test with ChatGPT Actions (use ngrok or similar for local testing)

### Test in Production

1. Deploy to Cloud Run
2. Update OpenAPI spec with production URL
3. Configure Custom GPT with production URL
4. Test end-to-end purchase flow

## Troubleshooting

### "Authentication failed"

- Verify API key is correct
- Check that Bearer token format is correct: `Bearer YOUR_API_KEY`
- Ensure API key has proper permissions

### "Endpoint not found"

- Verify OpenAPI spec server URL matches deployed API
- Check that all endpoints are accessible
- Verify CORS is configured correctly

### "Price changed, reapproval required"

- This is expected behavior when prices change between approval and confirmation
- ChatGPT should handle this by requesting reapproval from user

## Security Considerations

1. **API Key Security**: Never share API keys publicly
2. **Rate Limiting**: Consider implementing rate limits for production
3. **Input Validation**: ChatGPT will send user input - ensure proper validation
4. **Approval Workflow**: Always require explicit user approval before purchases

## Next Steps

- Customize GPT instructions for your use case
- Add error handling instructions
- Configure webhook notifications (if needed)
- Set up monitoring and logging

## Resources

- [ChatGPT Actions Documentation](https://platform.openai.com/docs/actions)
- [OpenAPI Specification](https://swagger.io/specification/)
- [CartPilot API Documentation](../README.md)

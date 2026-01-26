# Gemini Function Calling Integration

This directory contains the Python client for integrating CartPilot API with Google Gemini Function Calling.

## Overview

The `gemini_client.py` module provides a complete integration that allows Gemini to:

- Create purchase intents from natural language
- Search for products across merchants
- Manage checkout approval workflows
- Track order status

## Installation

```bash
pip install -r integrations/requirements.txt
```

Or install dependencies individually:

```bash
pip install google-generativeai httpx
```

## Quick Start

### 1. Set up API Keys

```bash
export GEMINI_API_KEY="your-gemini-api-key"
export CARTPILOT_API_URL="https://cartpilot-api-xxxx.run.app"
export CARTPILOT_API_KEY="your-cartpilot-api-key"
```

### 2. Basic Usage

```python
import asyncio
import os
import google.generativeai as genai
from integrations.gemini_client import CartPilotGeminiClient

async def main():
    # Configure Gemini
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    
    # Initialize CartPilot client
    client = CartPilotGeminiClient(
        cartpilot_api_url=os.getenv("CARTPILOT_API_URL"),
        api_key=os.getenv("CARTPILOT_API_KEY"),
    )
    
    # Get function declarations for Gemini
    functions = client.get_function_declarations()
    
    # Create Gemini model with functions
    model = genai.GenerativeModel(
        model_name="gemini-1.5-pro",
        tools=[{"function_declarations": functions}],
    )
    
    # Start chat
    chat = model.start_chat()
    
    # User message
    response = chat.send_message("I need wireless headphones under $100")
    
    # Handle function calls
    for candidate in response.candidates:
        for part in candidate.content.parts:
            if hasattr(part, "function_call") and part.function_call:
                # Execute function call
                result = await client.handle_function_call(part.function_call)
                
                # Send result back to Gemini
                chat.send_message(
                    genai.protos.FunctionResponse(
                        name=result["name"],
                        response=result["response"],
                    )
                )
                
                # Get Gemini's response
                final_response = chat.send_message("Continue")
                print(final_response.text)
    
    await client.close()

asyncio.run(main())
```

## Complete Example

See `example_chat.py` for a complete interactive chat example:

```bash
python integrations/example_chat.py
```

## Available Functions

The client provides 11 functions for Gemini:

### Intent Management
- `create_intent` - Create purchase intent from natural language
- `get_intent_offers` - Get offers from merchants for an intent

### Offer Management
- `get_offer_details` - Get detailed offer information

### Checkout Workflow
- `create_checkout` - Create checkout from offer
- `get_checkout` - Get checkout details
- `quote_checkout` - Get quote from merchant
- `request_approval` - Request approval and freeze receipt
- `approve_checkout` - Approve the purchase
- `confirm_checkout` - Execute the purchase

### Order Management
- `get_order_status` - Get order details and status
- `list_orders` - List orders with filtering

## Function Call Flow

### Example: Complete Purchase Flow

```python
# 1. User: "I need wireless headphones under $100"
#    → Gemini calls: create_intent(query="wireless headphones under $100")
#    → Returns: intent_id

# 2. Gemini calls: get_intent_offers(intent_id)
#    → Returns: List of offers with products

# 3. User: "Buy the Sony WH-1000XM4"
#    → Gemini calls: create_checkout(offer_id, items=[...])
#    → Returns: checkout_id

# 4. Gemini calls: quote_checkout(checkout_id, items=[...])
#    → Returns: Pricing information

# 5. Gemini calls: request_approval(checkout_id)
#    → Returns: Frozen receipt

# 6. User: "Approve the purchase"
#    → Gemini calls: approve_checkout(checkout_id)
#    → Returns: Approved checkout

# 7. Gemini calls: confirm_checkout(checkout_id)
#    → Returns: Order ID

# 8. Gemini calls: get_order_status(order_id)
#    → Returns: Order status and tracking
```

## Error Handling

The client automatically handles errors and returns them in a format Gemini can understand:

```python
result = await client.handle_function_call(function_call)

# Success case
{
    "name": "create_intent",
    "response": {
        "id": "intent-123",
        "query": "...",
        ...
    }
}

# Error case
{
    "name": "create_intent",
    "response": {
        "error": True,
        "error_code": "INTENT_CREATION_FAILED",
        "message": "Failed to create intent"
    }
}
```

## Configuration

### Environment Variables

- `GEMINI_API_KEY` - Google Gemini API key (required)
- `CARTPILOT_API_URL` - CartPilot API base URL (default: `http://localhost:8000`)
- `CARTPILOT_API_KEY` - CartPilot API key (required)

### Model Selection

Supported Gemini models:
- `gemini-1.5-pro` (recommended)
- `gemini-1.5-flash` (faster, lower cost)
- `gemini-pro` (legacy)

## Advanced Usage

### Custom Function Handling

You can extend the client to add custom logic:

```python
class CustomCartPilotClient(CartPilotGeminiClient):
    async def handle_function_call(self, function_call):
        # Add custom logging, validation, etc.
        print(f"Calling {function_call.name} with {function_call.args}")
        
        # Call parent implementation
        result = await super().handle_function_call(function_call)
        
        # Add custom processing
        if result["response"].get("error"):
            print(f"Error: {result['response']['message']}")
        
        return result
```

### Session Management

Track conversations with session IDs:

```python
session_id = "chat-session-123"

# Create intent with session
result = await client.api_client.create_intent(
    query="wireless headphones",
    session_id=session_id
)
```

## Troubleshooting

### "Function not found" error

- Ensure you're using the latest version of `google-generativeai`
- Check that function declarations are properly formatted
- Verify Gemini model supports function calling

### API connection errors

- Verify `CARTPILOT_API_URL` is correct
- Check that CartPilot API is running and accessible
- Ensure API key is valid

### Function call errors

- Check function parameters match the schema
- Verify required parameters are provided
- Review error messages in function response

## Testing

Run the example:

```bash
# Set environment variables
export GEMINI_API_KEY="your-key"
export CARTPILOT_API_URL="http://localhost:8000"
export CARTPILOT_API_KEY="dev-api-key-change-in-production"

# Run example
python integrations/gemini_client.py
```

## Resources

- [Gemini Function Calling Documentation](https://ai.google.dev/docs/function_calling)
- [Google Generative AI Python SDK](https://github.com/google/generative-ai-python)
- [CartPilot API Documentation](../README.md)

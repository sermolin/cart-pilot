# Integrations Module

## Overview

The integrations module provides example implementations for integrating CartPilot with various AI platforms and LLM services. Currently includes a complete integration for Google Gemini Function Calling.

## Purpose

- **Reference Implementation**: Provides working examples for integrating CartPilot with AI platforms
- **Gemini Integration**: Complete client for Google Gemini Function Calling
- **Extensibility**: Demonstrates patterns for building custom integrations

## Structure

```
integrations/
├── gemini_client.py      # Gemini Function Calling client
├── example_chat.py        # Interactive chat example
├── README.md              # Detailed integration guide
└── requirements.txt       # Python dependencies
```

## Gemini Function Calling Integration

### Overview

The `gemini_client.py` module provides a complete Python client for integrating CartPilot API with Google Gemini Function Calling capabilities. It allows Gemini models to interact with CartPilot to perform purchases, search products, and manage orders.

### Key Components

#### CartPilotGeminiClient

Main client class that:
- Converts CartPilot API endpoints to Gemini function declarations
- Handles function call execution
- Manages conversation state
- Provides error handling

#### CartPilotAPIClient

HTTP client wrapper for CartPilot REST API:
- Type-safe API calls
- Authentication handling
- Request/response formatting
- Error handling

### Available Functions

The integration exposes 11 functions to Gemini:

#### Intent Management
- `create_intent` - Create purchase intent from natural language
- `get_intent_offers` - Get offers from merchants for an intent

#### Offer Management
- `get_offer_details` - Get detailed offer information

#### Checkout Workflow
- `create_checkout` - Create checkout from offer
- `get_checkout` - Get checkout details
- `quote_checkout` - Get quote from merchant
- `request_approval` - Request approval and freeze receipt
- `approve_checkout` - Approve the purchase
- `confirm_checkout` - Execute the purchase

#### Order Management
- `get_order_status` - Get order details and status
- `list_orders` - List orders with filtering

### Usage Example

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

### Complete Purchase Flow

The integration supports the complete purchase workflow:

1. **Create Intent**: User describes what they want to buy
2. **Get Offers**: Retrieve products from merchants
3. **Create Checkout**: Initialize checkout with selected items
4. **Get Quote**: Retrieve pricing information
5. **Request Approval**: Freeze receipt and request approval
6. **Approve**: Approve the purchase
7. **Confirm**: Execute the purchase
8. **Track Order**: Monitor order status

### Error Handling

The client automatically handles errors and returns them in a format Gemini can understand:

```python
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

### Configuration

#### Environment Variables

- `GEMINI_API_KEY` - Google Gemini API key (required)
- `CARTPILOT_API_URL` - CartPilot API base URL (default: `http://localhost:8000`)
- `CARTPILOT_API_KEY` - CartPilot API key (required)

#### Supported Models

- `gemini-1.5-pro` (recommended)
- `gemini-1.5-flash` (faster, lower cost)
- `gemini-pro` (legacy)

### Interactive Example

Run the complete interactive chat example:

```bash
# Set environment variables
export GEMINI_API_KEY="your-gemini-api-key"
export CARTPILOT_API_URL="http://localhost:8000"
export CARTPILOT_API_KEY="dev-api-key-change-in-production"

# Run example
python integrations/example_chat.py
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

## Extending for Other Platforms

The integrations module demonstrates patterns for building custom integrations:

1. **API Client**: Create a client wrapper for CartPilot API
2. **Function Declarations**: Convert API endpoints to platform-specific function definitions
3. **Function Handler**: Implement function call execution
4. **Error Handling**: Format errors for the target platform
5. **Session Management**: Track conversation state

### Example: Adding ChatGPT Integration

```python
# Similar structure to gemini_client.py
class CartPilotChatGPTClient:
    def get_function_declarations(self):
        # Convert to OpenAI function format
        pass
    
    async def handle_function_call(self, function_call):
        # Execute and format response
        pass
```

## Dependencies

- `google-generativeai` - Google Gemini SDK
- `httpx` - HTTP client for async requests

## Testing

Run the example to test the integration:

```bash
python integrations/example_chat.py
```

## Documentation

See `integrations/README.md` for detailed documentation including:
- Installation instructions
- Complete usage examples
- Function reference
- Error handling guide
- Troubleshooting tips

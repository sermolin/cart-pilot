"""CartPilot integrations for LLM platforms.

This package provides integrations for:
- Gemini Function Calling (google.generativeai)
- ChatGPT Actions (via OpenAPI spec)
- MCP Server (via cartpilot-mcp)
"""

from integrations.gemini_client import CartPilotAPIClient, CartPilotGeminiClient

__all__ = ["CartPilotAPIClient", "CartPilotGeminiClient"]

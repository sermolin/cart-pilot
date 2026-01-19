"""CartPilot MCP Server main application.

Exposes CartPilot capabilities as MCP tools for AI agent interaction.
This is a thin adapter over the CartPilot REST API.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """MCP Server settings."""

    cartpilot_api_url: str = "http://cartpilot-api:8000"
    cartpilot_api_key: str = "dev-api-key-change-in-production"
    log_level: str = "INFO"

    class Config:
        """Pydantic configuration."""

        env_file = ".env"


settings = Settings()


def main() -> None:
    """Run the MCP server.

    This will be implemented in Module 9 with full MCP tool definitions.
    """
    print(f"CartPilot MCP Server starting...")
    print(f"CartPilot API URL: {settings.cartpilot_api_url}")
    print("MCP Server placeholder - full implementation in Module 9")


if __name__ == "__main__":
    main()

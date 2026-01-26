#!/usr/bin/env python3
"""Interactive chat example using CartPilot with Gemini Function Calling.

This example demonstrates a complete interactive shopping assistant
powered by Gemini and CartPilot.

Usage:
    export GEMINI_API_KEY="your-gemini-api-key"
    export CARTPILOT_API_URL="http://localhost:8000"
    export CARTPILOT_API_KEY="dev-api-key-change-in-production"
    
    python integrations/example_chat.py
"""

import asyncio
import os
import sys
from typing import Optional

import google.generativeai as genai
from integrations.gemini_client import CartPilotGeminiClient


class ShoppingAssistant:
    """Interactive shopping assistant using Gemini and CartPilot."""

    def __init__(self):
        """Initialize the shopping assistant."""
        # Check for required environment variables
        gemini_key = os.getenv("GEMINI_API_KEY")
        cartpilot_url = os.getenv("CARTPILOT_API_URL", "http://localhost:8000")
        cartpilot_key = os.getenv("CARTPILOT_API_KEY", "dev-api-key-change-in-production")

        if not gemini_key:
            print("Error: GEMINI_API_KEY environment variable not set")
            sys.exit(1)

        # Configure Gemini
        genai.configure(api_key=gemini_key)

        # Initialize CartPilot client
        self.client = CartPilotGeminiClient(cartpilot_api_url=cartpilot_url, api_key=cartpilot_key)

        # Get function declarations
        functions = self.client.get_function_declarations()

        # Create Gemini model with functions
        self.model = genai.GenerativeModel(
            model_name="gemini-1.5-pro",
            tools=[{"function_declarations": functions}],
        )

        self.chat: Optional[genai.ChatSession] = None

    async def start(self):
        """Start the chat session."""
        self.chat = self.model.start_chat(
            history=[
                {
                    "role": "user",
                    "parts": [
                        "You are a helpful shopping assistant powered by CartPilot. "
                        "You help users find and purchase products. "
                        "Always explain what you're doing at each step. "
                        "Never make purchases without explicit user approval. "
                        "Be friendly and helpful."
                    ],
                },
                {
                    "role": "model",
                    "parts": [
                        "Hello! I'm your shopping assistant. I can help you find products "
                        "and make purchases. What would you like to buy today?"
                    ],
                },
            ]
        )

        print("=" * 60)
        print("CartPilot Shopping Assistant")
        print("Powered by Gemini Function Calling")
        print("=" * 60)
        print("\nType 'quit' or 'exit' to end the conversation.\n")

    async def process_message(self, user_message: str) -> str:
        """Process a user message and return assistant response.

        Args:
            user_message: User's message

        Returns:
            Assistant's response text
        """
        if not self.chat:
            await self.start()

        # Send user message
        response = self.chat.send_message(user_message)

        # Handle function calls
        function_calls_handled = False
        for candidate in response.candidates:
            for part in candidate.content.parts:
                if hasattr(part, "function_call") and part.function_call:
                    function_calls_handled = True
                    await self._handle_function_call(part.function_call)

        # If function calls were handled, get the final response
        if function_calls_handled:
            final_response = self.chat.send_message("Continue with your response to the user.")
            return final_response.text

        return response.text

    async def _handle_function_call(self, function_call):
        """Handle a function call from Gemini.

        Args:
            function_call: Function call object from Gemini
        """
        print(f"\n[Function Call] {function_call.name}")
        print(f"  Arguments: {dict(function_call.args)}\n")

        # Execute function call
        result = await self.client.handle_function_call(function_call)

        # Check for errors
        if result["response"].get("error"):
            error_msg = result["response"].get("message", "Unknown error")
            print(f"  [Error] {error_msg}\n")
        else:
            print(f"  [Success] Function executed\n")

        # Send result back to Gemini
        self.chat.send_message(
            genai.protos.FunctionResponse(
                name=result["name"],
                response=result["response"],
            )
        )

    async def run(self):
        """Run the interactive chat loop."""
        await self.start()

        while True:
            try:
                # Get user input
                user_input = input("\nYou: ").strip()

                if not user_input:
                    continue

                if user_input.lower() in ["quit", "exit", "q"]:
                    print("\nGoodbye! Thanks for shopping with CartPilot!")
                    break

                # Process message
                print("\nAssistant: ", end="", flush=True)
                response = await self.process_message(user_input)
                print(response)

            except KeyboardInterrupt:
                print("\n\nGoodbye!")
                break
            except Exception as e:
                print(f"\n[Error] {e}")
                import traceback

                traceback.print_exc()

        await self.client.close()


async def main():
    """Main entry point."""
    assistant = ShoppingAssistant()
    await assistant.run()


if __name__ == "__main__":
    asyncio.run(main())

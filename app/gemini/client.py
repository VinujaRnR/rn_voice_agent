"""Gemini API client configuring structured output with GeminiResponse and cross-field validation."""
import os
import json
import logging
from typing import Optional, List, Dict, Any
from google import genai
from google.genai import types
from pydantic import ValidationError

from app.config import settings
from app.gemini.prompts import SYSTEM_INSTRUCTION
from app.gemini.schemas import GeminiResponse, DeviceCommand

logger = logging.getLogger(__name__)


class GeminiClient:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.gemini_api_key or os.environ.get("GEMINI_API_KEY", "")
        self.model = model or settings.gemini_model or os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")
        self._client: Optional[genai.Client] = None

    @property
    def client(self) -> genai.Client:
        if self._client is None:
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    async def generate_response(
        self,
        prompt: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None
    ) -> GeminiResponse:
        """Generate structured response using GeminiResponse schema with cross-field validation."""
        # Check for unconfigured API key
        if not self.api_key or self.api_key.startswith("YOUR_API_KEY"):
            return GeminiResponse(
                mode="answer",
                speech="Gemini API key is not configured. Please add your key to .env.",
                command=None,
                missing_fields=[]
            )

        try:
            # Build conversation context
            full_prompt_lines = []
            if conversation_history:
                full_prompt_lines.append("Previous Conversation:")
                for msg in conversation_history[-6:]:
                    role = "User" if msg.get("role") == "user" else "Assistant"
                    full_prompt_lines.append(f"{role}: {msg.get('content', '')}")
                full_prompt_lines.append("\nCurrent User Input:")

            full_prompt_lines.append(prompt)
            contents = "\n".join(full_prompt_lines)

            # Configure structured JSON output with GeminiResponse
            config = types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                response_mime_type="application/json",
                response_schema=GeminiResponse,
            )

            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=contents,
                config=config,
            )

            if not response.text:
                return GeminiResponse(
                    mode="answer",
                    speech="No response received from Gemini.",
                    command=None,
                    missing_fields=[]
                )

            # Parse and validate with Pydantic (including cross-field validation)
            parsed_data = json.loads(response.text)
            gemini_response = GeminiResponse.model_validate(parsed_data)
            return gemini_response

        except ValidationError as ve:
            logger.error(f"Gemini response failed cross-field validation: {ve}")
            # Invalid response is caught here and blocked from reaching executor
            return GeminiResponse(
                mode="answer",
                speech="The generated command failed safety validation and was rejected.",
                command=None,
                missing_fields=[]
            )

        except Exception as e:
            err_msg = str(e)
            logger.error(f"Gemini API request failed: {err_msg}")
            if "API key not valid" in err_msg or "API_KEY_INVALID" in err_msg:
                return GeminiResponse(
                    mode="answer",
                    speech="The provided Gemini API key in .env is invalid. Please check your Google AI Studio key.",
                    command=None,
                    missing_fields=[]
                )
            return GeminiResponse(
                mode="answer",
                speech="I encountered an error processing your request.",
                command=None,
                missing_fields=[]
            )

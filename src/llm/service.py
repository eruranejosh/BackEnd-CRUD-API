# Import os so we can read our LLM settings from the environment
import os

# Import json so we can convert the LLM's text response into Python data
import json

# Import the schema that defines the exact property output we allow
from src.llm.schema import PropertyEnrichment

# Import Path so we can locate files inside our project
from pathlib import Path

# Import dotenv so variables from .env are available
from dotenv import load_dotenv

# Import the OpenAI client
from openai import OpenAI


# Load variables from the .env file
load_dotenv()


# Find the root directory of the project
PROJECT_ROOT = Path(__file__).resolve().parents[2]


# Point to our versioned property-enrichment prompt
PROMPT_PATH = PROJECT_ROOT / "prompts" / "property-enrich-v1.md"


def load_property_prompt() -> str:
    # Read the prompt file and return its contents as text
    return PROMPT_PATH.read_text(encoding="utf-8")


def build_messages(property_text: str) -> list[dict[str, str]]:
    # Load our trusted instructions from the versioned prompt
    system_prompt = load_property_prompt()

    # Keep the property description separate from our trusted instructions
    user_message = property_text

    # Return the system and user messages expected by the LLM
    return [
        {
            "role": "system",
            "content": system_prompt,
        },
        {
            "role": "user",
            "content": user_message,
        },
    ]


def call_llm(property_text: str) -> str:
    # Create the OpenAI-compatible client using our OpenRouter settings
    client = OpenAI(
        base_url=os.getenv("LLM_BASE_URL"),
        api_key=os.getenv("LLM_API_KEY"),
    )

    # Build the system and user messages for this property
    messages = build_messages(property_text)

    # Send the request to the configured model
    response = client.chat.completions.create(
        model=os.getenv("LLM_MODEL"),
        messages=messages,

        # Keep the model's output focused and consistent
        temperature=0.1,
    )

    # Return only the model's text response
    return response.choices[0].message.content
def clean_llm_response(raw_response: str) -> str:
    # Remove unnecessary whitespace from the model response
    cleaned = raw_response.strip()

    # Remove a Markdown JSON code fence if the model included one
    if cleaned.startswith("```json"):
        cleaned = cleaned[len("```json"):].strip()

    # Remove a generic Markdown code fence if the model included one
    if cleaned.startswith("```"):
        cleaned = cleaned[len("```"):].strip()

    # Remove the closing Markdown code fence
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].strip()

    # Return the cleaned response for JSON parsing
    return cleaned

def parse_llm_response(raw_response: str) -> dict:
    # Clean the model response before attempting to parse it
    cleaned_response = clean_llm_response(raw_response)

    # Convert the JSON text into a Python dictionary
    parsed_response = json.loads(cleaned_response)

    # Return the parsed dictionary
    return parsed_response
def validate_llm_response(parsed_response: dict) -> PropertyEnrichment:
    # Validate the parsed dictionary against our strict Pydantic schema
    validated_response = PropertyEnrichment.model_validate(parsed_response)

    # Return the validated property object
    return validated_response
def repair_llm_response(raw_response: str, validation_error: str) -> str:
    # Create the OpenAI-compatible client using our OpenRouter settings
    client = OpenAI(
        base_url=os.getenv("LLM_BASE_URL"),
        api_key=os.getenv("LLM_API_KEY"),
    )

    # Create a separate repair instruction
    repair_prompt = f"""
# Explain the repair task to the LLM
Your previous response failed validation.

# Tell the LLM what went wrong
Validation error:
{validation_error}

# Give the LLM the response that needs to be repaired
Previous response:
{raw_response}

# Tell the LLM exactly what to return
Return ONLY valid JSON matching the required property enrichment schema.
Do not add Markdown.
Do not add explanations.
Do not invent missing information.
"""

    # Ask the LLM to correct its previous response
    response = client.chat.completions.create(
        model=os.getenv("LLM_MODEL"),
        messages=[
            {
                "role": "system",
                "content": repair_prompt,
            }
        ],
        temperature=0.1,
    )

    # Return only the repaired text from the LLM
    return response.choices[0].message.content
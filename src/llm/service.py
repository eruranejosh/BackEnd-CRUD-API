# Import os so we can read our LLM settings from the environment
import os

# Import json so we can convert LLM responses into Python data
import json

# Import time so we can measure request duration and pause between retries
import time

# Import random so we can add jitter to retry delays
import random

# Import datetime so we can record when each LLM call happened
from datetime import datetime, timezone

# Import Path so we can locate files inside our project
from pathlib import Path

# Import dotenv so variables from .env are available
from dotenv import load_dotenv

# Import the OpenAI-compatible client
from openai import OpenAI

# Import the schema that defines the exact property output we allow
from src.llm.schema import PropertyEnrichment


# Load variables from the .env file
load_dotenv()


# Find the root directory of the project
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Point to our versioned property-enrichment prompt
PROMPT_PATH = PROJECT_ROOT / "prompts" / "property-enrich-v1.md"

# Store one cost record per LLM call
COST_LOG_PATH = PROJECT_ROOT / "logs" / "llm_costs.jsonl"


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
            # Give the model its trusted instructions
            "role": "system",
            "content": system_prompt,
        },
        {
            # Give the model the untrusted property description separately
            "role": "user",
            "content": user_message,
        },
    ]


def log_llm_cost(
    response,
    duration_ms: int,
    repair: bool = False,
):
    # Get token usage information returned by the provider
    usage = response.usage

    # Build one structured record for this LLM call
    record = {
        # Record when the LLM call happened
        "timestamp": datetime.now(timezone.utc).isoformat(),

        # Record which prompt version was used
        "prompt_version": "property-enrich-v1",

        # Record the configured model
        "model": os.getenv("LLM_MODEL"),

        # Record the number of input tokens
        "input_tokens": usage.prompt_tokens if usage else None,

        # Record the number of output tokens
        "output_tokens": usage.completion_tokens if usage else None,

        # Record the total number of tokens
        "total_tokens": usage.total_tokens if usage else None,

        # Record how long the request took
        "duration_ms": duration_ms,

        # Identify whether this was a repair request
        "repair": repair,
    }

    # Open the cost log in append mode
    with open(
        COST_LOG_PATH,
        "a",
        encoding="utf-8",
    ) as file:

        # Write exactly one JSON object per line
        file.write(
            json.dumps(record) + "\n"
        )


def call_llm(property_text: str) -> str:
    # Create the OpenAI-compatible client using our OpenRouter settings
    client = OpenAI(
        base_url=os.getenv("LLM_BASE_URL"),
        api_key=os.getenv("LLM_API_KEY"),

        # Disable SDK automatic retries because we handle retries ourselves
        max_retries=0,
    )

    # Build the system and user messages for this property
    messages = build_messages(property_text)

    # Allow one initial attempt plus three retry attempts
    max_attempts = 4

    # Try the LLM request up to four times
    for attempt in range(max_attempts):

        try:
            # Start the timer before sending the LLM request
            start_time = time.perf_counter()

            # Send the request to the configured model
            response = client.chat.completions.create(
                model=os.getenv("LLM_MODEL"),
                messages=messages,

                # Keep the model's output focused and consistent
                temperature=0.1,

                # Stop waiting if the LLM takes longer than 30 seconds
                timeout=30,
            )

            # Calculate how long the request took in milliseconds
            duration_ms = round(
                (time.perf_counter() - start_time) * 1000
            )

            # Record the model usage and timing information
            log_llm_cost(
                response=response,
                duration_ms=duration_ms,
                repair=False,
            )

            # Return the successful LLM response
            return response.choices[0].message.content

        except Exception as error:

            # Get the HTTP status code when the provider supplies one
            status_code = getattr(
                error,
                "status_code",
                None,
            )

            # Check whether the error appears to be a timeout
            is_timeout = (
                "timeout" in str(error).lower()
                or "timed out" in str(error).lower()
            )

            # These temporary HTTP errors are safe to retry
            retryable_status = status_code in {
                429,
                500,
                502,
                503,
                504,
            }

            # Do not retry authentication, permission, or other permanent errors
            if not is_timeout and not retryable_status:
                raise

            # Stop when the final attempt has already failed
            if attempt == max_attempts - 1:
                raise

            # Try to get the provider's Retry-After instruction
            retry_after = None

            # Get the provider response attached to the exception
            error_response = getattr(
                error,
                "response",
                None,
            )

            # Read the response headers when they are available
            if error_response is not None:
                headers = getattr(
                    error_response,
                    "headers",
                    {},
                )

                # Get the Retry-After header
                retry_after = headers.get(
                    "retry-after"
                )

            # Use the provider's requested delay when available
            if retry_after is not None:

                try:
                    # Convert Retry-After into seconds
                    delay = float(retry_after)

                except (TypeError, ValueError):

                    # Fall back to exponential backoff if the header is invalid
                    backoff = 2 ** attempt

                    # Add a small random delay to reduce retry collisions
                    jitter = random.uniform(0, 0.5)

                    # Combine the backoff and jitter
                    delay = backoff + jitter

            else:

                # Calculate exponential backoff when Retry-After is unavailable
                # first retry = approximately 1 second
                # second retry = approximately 2 seconds
                # third retry = approximately 4 seconds
                backoff = 2 ** attempt

                # Add a small random delay to reduce retry collisions
                jitter = random.uniform(0, 0.5)

                # Combine the backoff and jitter
                delay = backoff + jitter

            # Wait before trying the request again
            time.sleep(delay)

    # This should never be reached
    raise RuntimeError(
        "LLM request failed after all retry attempts"
    )


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


def parse_llm_response(
    raw_response: str,
) -> dict:
    # Clean the model response before attempting to parse it
    cleaned_response = clean_llm_response(
        raw_response
    )

    # Convert the JSON text into a Python dictionary
    parsed_response = json.loads(
        cleaned_response
    )

    # Return the parsed dictionary
    return parsed_response


def validate_llm_response(
    parsed_response: dict,
) -> PropertyEnrichment:
    # Validate the parsed dictionary against our strict Pydantic schema
    validated_response = PropertyEnrichment.model_validate(
        parsed_response
    )

    # Return the validated property object
    return validated_response


def repair_llm_response(
    raw_response: str,
    validation_error: str,
) -> str:

    # Create the OpenAI-compatible client using our OpenRouter settings
    client = OpenAI(
        base_url=os.getenv("LLM_BASE_URL"),
        api_key=os.getenv("LLM_API_KEY"),

        # Disable SDK automatic retries
        max_retries=0,
    )

    # Load the trusted property-enrichment instructions
    system_prompt = load_property_prompt()

    # Create focused instructions for repairing the failed response
    repair_prompt = f"""
Your previous response failed to produce valid property enrichment JSON.

Required output:

{{
  "property_type": "apartment | house | duplex | land | office | shop | other",
  "bedrooms": "integer or null",
  "location": "string or null",
  "condition": "new | renovated | fair | needs_renovation | unknown",
  "servicing": "serviced | unserviced | unknown",
  "summary": "short string",
  "confidence": "number between 0.0 and 1.0",
  "needs_review": "boolean"
}}

Rules:
- Return exactly one JSON object.
- Return JSON only.
- Do not return Markdown.
- Do not return a safety assessment.
- Do not return "status".
- Do not return "message".
- Do not return "repair_task".
- Do not return explanations.
- Do not add fields outside the required schema.
- Do not invent missing property information.
- Use null or "unknown" when information is unavailable.
- Set needs_review to true when you are unsure.

Previous response:
{raw_response}

Validation error:
{validation_error}

Return ONLY the corrected property enrichment JSON object.
"""

    # Start the timer before sending the repair request
    start_time = time.perf_counter()

    # Send the repair request to the LLM
    response = client.chat.completions.create(
        model=os.getenv("LLM_MODEL"),
        messages=[
            {
                # Keep the trusted property rules in the system message
                "role": "system",
                "content": system_prompt,
            },
            {
                # Keep repair instructions and failed output separate
                "role": "user",
                "content": repair_prompt,
            },
        ],
        temperature=0.1,

        # Stop waiting if the repair request takes longer than 30 seconds
        timeout=30,
    )

    # Calculate how long the repair request took
    duration_ms = round(
        (time.perf_counter() - start_time) * 1000
    )

    # Record the repair request in the cost log
    log_llm_cost(
        response=response,
        duration_ms=duration_ms,
        repair=True,
    )

    # Return only the repaired text from the LLM
    return response.choices[0].message.content
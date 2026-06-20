"""Extracts commitments (promises) made in raw conversation logs using LLMs."""

import logging
import uuid
from typing import Optional

from domain.enums import CommitmentStatus
from domain.models import Message, Commitment
from llm.llm_client import LLMClient
from llm.prompt_loader import PromptLoader
from llm.response_parser import ResponseParser, ResponseParseError, ResponseValidationError

logger = logging.getLogger(__name__)


def normalize_owner_name(name: str) -> str:
    """Standardize owner names to their first names (e.g. Siddharth Rao -> Siddharth)."""
    if not name:
        return "Unknown"
    name_lower = name.lower()
    if "siddharth" in name_lower:
        return "Siddharth"
    if "ananya" in name_lower:
        return "Ananya"
    if "karan" in name_lower:
        return "Karan"
    if "neha" in name_lower:
        return "Neha"
    if "rohan" in name_lower:
        return "Rohan"
    # Fallback to capitalize first word
    parts = name.strip().split()
    if parts:
        return parts[0].capitalize()
    return name.strip()


class CommitmentExtractor:
    """Performs daily batch extraction of commitments from raw conversation logs using LLM."""

    def __init__(
        self,
        llm_client: LLMClient,
        prompt_loader: Optional[PromptLoader] = None,
        response_parser: Optional[ResponseParser] = None
    ) -> None:
        """Initialize the CommitmentExtractor.

        Args:
            llm_client: The LLM client for sending prompts.
            prompt_loader: Optional utility to load prompt templates.
            response_parser: Optional utility to parse LLM responses.
        """
        self.llm_client = llm_client
        self.prompt_loader = prompt_loader or PromptLoader()
        self.response_parser = response_parser or ResponseParser()

    def _format_messages(self, messages: list[Message]) -> str:
        """Format a list of Message objects for the LLM."""
        lines = []
        for msg in messages:
            # Include timestamp, sender, and text
            lines.append(f"[{msg.timestamp.strftime('%H:%M:%S')}] {msg.sender}: {msg.text}")
        return "\n".join(lines)

    def extract_commitments(self, messages: list[Message], report_date: str) -> list[Commitment]:
        """Extract commitments from a batch of messages for a single day.

        Args:
            messages: List of Message domain objects for the day.
            report_date: Date string (YYYY-MM-DD).

        Returns:
            A list of extracted Commitment domain objects.
        """
        if not messages:
            logger.info("No messages provided for commitment extraction.")
            return []

        formatted_msg_content = self._format_messages(messages)
        logger.info("Extracting commitments for report date %s...", report_date)

        try:
            # Load and render prompt
            prompt = self.prompt_loader.render_prompt(
                prompt_name="commitment_extraction",
                variables={
                    "current_date": report_date,
                    "messages": formatted_msg_content
                }
            )

            # Generate and parse with retries
            from llm.response_parser import ResponseParseError, ResponseValidationError
            max_retries = 3
            parsed_data = None
            for attempt in range(1, max_retries + 1):
                try:
                    logger.info("Extracting commitments for %s (attempt %d/%d)", report_date, attempt, max_retries)
                    # Generate response from LLM
                    response_text = self.llm_client.generate(prompt)

                    # Parse the response (can be list of dicts)
                    parsed_data = self.response_parser.parse_json_response(response_text)
                    if not isinstance(parsed_data, list):
                        raise ResponseValidationError("Expected a JSON list of commitments, got: " + str(type(parsed_data)))
                    break
                except (ResponseParseError, ResponseValidationError) as e:
                    if attempt == max_retries:
                        raise
                    logger.warning(
                        "Validation failed for commitments on date %s (attempt %d/%d). Error: %s. Retrying...",
                        report_date, attempt, max_retries, str(e)
                    )
            
            commitments = []
            if isinstance(parsed_data, list):
                for item in parsed_data:
                    if not isinstance(item, dict):
                        continue
                    
                    owner = normalize_owner_name(item.get("owner", "Unknown"))
                    description = item.get("description", "").strip()
                    due_date = item.get("due_date", report_date).strip()
                    context = item.get("context", "").strip()

                    # Basic validation of due date format, fall back to report_date if invalid
                    import re
                    if not re.match(r"^\d{4}-\d{2}-\d{2}$", due_date):
                        due_date = report_date

                    if description:
                        commitment = Commitment(
                            commitment_id=f"cmt-{uuid.uuid4()}",
                            owner=owner,
                            description=description,
                            created_date=report_date,
                            due_date=due_date,
                            status=CommitmentStatus.OPEN,
                            context=context
                        )
                        commitments.append(commitment)
            
            logger.info("Successfully extracted %d commitments for %s", len(commitments), report_date)
            return commitments

        except Exception as e:
            logger.warning(
                "Failed to extract commitments for date '%s'. Error ignored to prevent pipeline crash. Error: %s",
                report_date, str(e)
            )
            return []

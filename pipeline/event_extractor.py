"""Extracts operational events of interest from conversation threads using LLMs."""

import logging
from typing import List, Optional

from domain.models import Event, Thread
from llm.llm_client import LLMClient
from llm.prompt_loader import PromptLoader
from llm.response_parser import ResponseParser

logger = logging.getLogger(__name__)


class EventExtractor:
    """Uses an LLM to analyze conversation threads and extract structured operational events."""

    def __init__(
        self,
        llm_client: LLMClient,
        prompt_loader: Optional[PromptLoader] = None,
        response_parser: Optional[ResponseParser] = None
    ) -> None:
        """Initialize the EventExtractor.

        Args:
            llm_client: The LLM client for sending prompts.
            prompt_loader: Optional utility to load prompt templates.
            response_parser: Optional utility to parse LLM responses.
        """
        self.llm_client = llm_client
        self.prompt_loader = prompt_loader or PromptLoader()
        self.response_parser = response_parser or ResponseParser()

    def _format_thread(self, thread: Thread) -> str:
        """Format a Thread object into a structured text representation for the LLM.

        Args:
            thread: The conversation thread.

        Returns:
            A formatted string containing the full context of the thread.
        """
        lines = [
            f"Thread ID: {thread.id}",
            f"Date: {thread.date}",
            f"Participants: {', '.join(thread.participants)}",
            "Messages:"
        ]
        for idx, msg in enumerate(thread.messages):
            msg_role = "Parent Message" if idx == 0 else f"Reply {idx}"
            lines.append(f"  [{msg.timestamp.isoformat()}] {msg_role} by {msg.sender}:")
            lines.append(f"    {msg.text}")
        return "\n".join(lines)

    def extract_from_thread(self, thread: Thread) -> List[Event]:
        """Extract operational events from a single conversation thread.

        Args:
            thread: The Thread domain object to analyze.

        Returns:
            A list of extracted Event domain objects. Returns an empty list
            if no events are found or if the LLM output is malformed/unparseable.
        """
        logger.info("Extracting events from thread: %s", thread.id)
        thread_content = self._format_thread(thread)

        try:
            # Load and render prompt
            prompt = self.prompt_loader.render_prompt(
                prompt_name="event_extraction",
                variables={"thread_content": thread_content}
            )

            # Generate response from LLM
            response_text = self.llm_client.generate(prompt)

            # Parse and validate the response
            events = self.response_parser.parse_events(response_text)

            # Link the events back to this thread and update participants if empty
            for event in events:
                event.source_thread_id = thread.id
                if thread.created_at:
                    event.created_at = thread.created_at
                # If participants list was not extracted or empty, fallback to thread participants
                if not event.participants:
                    event.participants = list(thread.participants)

            logger.info("Successfully extracted %d events from thread: %s", len(events), thread.id)
            return events

        except Exception as e:
            logger.warning(
                "Failed to extract events from thread '%s'. Output ignored to prevent pipeline crash. Error: %s",
                thread.id, str(e)
            )
            # Gracefully handle validation/parsing/LLM errors
            return []

    def extract_from_threads(self, threads: List[Thread]) -> List[Event]:
        """Extract operational events from a list of conversation threads.

        Args:
            threads: A list of Thread domain objects to analyze.

        Returns:
            A merged list of all valid extracted Event domain objects.
        """
        all_events = []
        if not threads:
            logger.info("No threads provided for event extraction.")
            return all_events

        for thread in threads:
            events = self.extract_from_thread(thread)
            all_events.extend(events)

        logger.info("Completed extraction across %d threads. Total events extracted: %d", len(threads), len(all_events))
        return all_events

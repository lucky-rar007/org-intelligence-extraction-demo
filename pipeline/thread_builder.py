"""Builds conversation threads from raw message logs."""

import logging
from typing import List

from domain.models import Message, Thread

logger = logging.getLogger(__name__)


class ThreadBuilder:
    """Builds conversation threads from flat lists of domain messages.

    This class reconstructs threads by linking parent messages and replies
    based on the Microsoft Graph API identifiers.
    """

    def build_threads(self, messages: List[Message]) -> List[Thread]:
        """Group a list of messages into conversation threads.

        Args:
            messages: A list of Message domain objects.

        Returns:
            A list of reconstructed Thread domain objects.
        """
        if not messages:
            logger.info("No messages provided to build threads.")
            return []

        parents_map = {}
        replies_by_parent = {}

        # First pass: identify and group parent messages
        for msg in messages:
            if not msg.id:
                logger.warning("Malformed message detected: missing unique identifier 'id'. Skipping.")
                continue

            # Check if this is a parent message (reply_to is None or empty)
            if not msg.reply_to:
                if msg.id in parents_map:
                    logger.warning("Duplicate parent message ID detected: %s. Using the first instance.", msg.id)
                    continue
                parents_map[msg.id] = msg
                replies_by_parent[msg.id] = []

        # Second pass: group replies to their respective parents
        for msg in messages:
            if not msg.id:
                continue

            if msg.reply_to:
                parent_id = msg.reply_to
                if parent_id in parents_map:
                    replies_by_parent[parent_id].append(msg)
                else:
                    logger.warning(
                        "Orphan reply detected: message '%s' is a reply to parent ID '%s', "
                        "which was not found in the message list.",
                        msg.id, parent_id
                    )

        # Build Thread objects
        threads = []
        for parent_id, parent_msg in parents_map.items():
            associated_replies = replies_by_parent[parent_id]

            # Sort replies chronologically (oldest reply first)
            # Safe because Message.timestamp is a required datetime object
            associated_replies.sort(key=lambda m: m.timestamp)

            # Reconstructed thread contains the parent message followed by replies
            thread_messages = [parent_msg] + associated_replies

            # Collect unique participants preserving order of appearance
            participants = []
            for m in thread_messages:
                if m.sender:
                    sender_name = m.sender.strip()
                    if sender_name and sender_name not in participants:
                        participants.append(sender_name)

            try:
                # Thread date is the date of the initiating parent message
                thread_date = parent_msg.timestamp.date()

                thread = Thread(
                    id=parent_id,
                    date=thread_date,
                    messages=thread_messages,
                    participants=participants
                )
                threads.append(thread)
            except Exception as e:
                logger.error("Failed to build Thread for parent ID %s: %s", parent_id, str(e))
                # Do not crash the pipeline
                continue

        logger.info("Successfully reconstructed %d threads from %d messages.", len(threads), len(messages))
        return threads

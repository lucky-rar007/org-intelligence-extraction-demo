import json
import datetime
from pathlib import Path
from typing import List

# Set PYTHONPATH style context dynamically
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
# Temporarily set model to llama3.1:8b which is locally installed in Ollama
config.OLLAMA_MODEL = "llama3.1:8b"

from domain.models import Message
from pipeline.thread_builder import ThreadBuilder
from pipeline.event_extractor import EventExtractor
from llm.llm_client import LLMClient

def load_raw_messages(file_path: Path) -> List[Message]:
    """Load raw MS Graph API message responses from a JSON file and convert to Message domain models."""
    print(f"Loading raw messages from: {file_path.name}...")
    with open(file_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)
    
    messages = []
    for raw_msg in raw_data:
        # Extract sender name safely from nested Graph API structure
        sender = raw_msg.get("from", {}).get("user", {}).get("displayName", "System")
        
        # Extract text body safely
        text = raw_msg.get("body", {}).get("content", "")
        
        # Parse ISO datetime
        created_time_str = raw_msg.get("createdDateTime")
        # Handle trailing Z for python datetime compatibility
        if created_time_str.endswith("Z"):
            created_time_str = created_time_str[:-1] + "+00:00"
        timestamp = datetime.datetime.fromisoformat(created_time_str)
        
        # Build domain Message model
        msg = Message(
            id=raw_msg.get("id"),
            sender=sender,
            text=text,
            timestamp=timestamp,
            reply_to=raw_msg.get("replyToId")
        )
        messages.append(msg)
    
    return messages

def main():
    # 1. Load messages from the first raw file (e.g. 11-06-2026.json)
    raw_file = config.RAW_DATA_DIR / "11-06-2026.json"
    if not raw_file.exists():
        print(f"Error: Raw file {raw_file} does not exist.")
        return
        
    messages = load_raw_messages(raw_file)
    print(f"Loaded {len(messages)} raw messages.")

    # 2. Build threads
    print("\nBuilding threads...")
    builder = ThreadBuilder()
    threads = builder.build_threads(messages)
    print(f"Reconstructed {len(threads)} conversation threads.")

    # Save reconstructed threads to data/processed/
    processed_threads_file = config.PROCESSED_DATA_DIR / raw_file.name
    threads_data = [json.loads(t.model_dump_json()) for t in threads]
    with open(processed_threads_file, "w", encoding="utf-8") as f:
        json.dump(threads_data, f, indent=2)
    print(f"Saved reconstructed threads to: {processed_threads_file}")

    # 3. Setup LLM and Extract Events
    print("\nInitializing LLM client and extracting events...")
    try:
        # Create LLM client
        llm_client = LLMClient()
        # Create event extractor
        extractor = EventExtractor(llm_client=llm_client)
        
        # We will extract events from the first 5 threads to show a quick demo
        threads_to_analyze = threads[:5]
        print(f"Sending first {len(threads_to_analyze)} threads to local Ollama (model: {config.OLLAMA_MODEL}) for extraction...")
        
        extracted_events = extractor.extract_from_threads(threads_to_analyze)
        
        # Save extracted events to outputs/events/
        events_output_file = config.EVENTS_OUTPUT_DIR / raw_file.name
        events_data = [json.loads(e.model_dump_json()) for e in extracted_events]
        with open(events_output_file, "w", encoding="utf-8") as f:
            json.dump(events_data, f, indent=2)
        print(f"Saved extracted events to: {events_output_file}")
        
        print("\n" + "="*50)
        print(f"EXTRACTED EVENTS SUMMARY ({len(extracted_events)} events found)")
        print("="*50)
        for idx, event in enumerate(extracted_events):
            print(f"\nEvent {idx+1}:")
            print(f"  Title:            {event.title}")
            print(f"  Type:             {event.event_type.value}")
            print(f"  Severity:         {event.severity.value}")
            print(f"  Confidence:       {event.confidence_score}")
            print(f"  Source Thread:    {event.source_thread_id}")
            print(f"  Affected Areas:   {event.affected_areas}")
            print(f"  Participants:     {event.participants}")
            print(f"  Description:      {event.description}")
        print("="*50)
        
    except Exception as e:
        print(f"\nError running event extraction: {e}")


if __name__ == "__main__":
    main()

import json
from pathlib import Path
import sys

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.similarity import title_similarity, normalize_text

def improved_title_similarity(a: str, b: str) -> float:
    # Stop words and noise words to ignore
    stop_words = {
        "issue", "issues", "problem", "problems", "error", "errors", "failed", "failure",
        "delay", "delays", "sync", "fix", "verification", "report", "reports", "concept",
        "update", "updates", "reminder", "reminders", "for", "and", "on", "in", "to", "the",
        "a", "an", "of", "about", "with", "from", "at", "by", "is", "was", "were", "be", "been"
    }
    
    def get_clean_tokens(text: str):
        normalized = normalize_text(text)
        tokens = normalized.split()
        # Filter stop words
        filtered = [t for t in tokens if t not in stop_words]
        # Also clean plurals slightly
        cleaned = []
        for t in filtered:
            if t.endswith("s") and len(t) > 3:
                cleaned.append(t[:-1])
            else:
                cleaned.append(t)
        return set(cleaned)

    tokens_a = get_clean_tokens(a)
    tokens_b = get_clean_tokens(b)
    
    if not tokens_a or not tokens_b:
        return 0.0
        
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    
    jaccard = len(intersection) / len(union)
    
    # Entity boosting: if both mention specific known entities, boost the score
    entities = [
        {"payment", "gateway", "paytm", "sdk"},
        {"staging", "database", "connection", "caching", "redis", "pool", "disk"},
        {"client", "abc"},
        {"client", "xyz"},
        {"android", "login", "proguard", "app"},
        {"cors"}
    ]
    
    boost = 0.0
    for entity_set in entities:
        # Check if both titles have at least one word from the entity set
        has_a = any(w in tokens_a for w in entity_set)
        has_b = any(w in tokens_b for w in entity_set)
        if has_a and has_b:
            # If they share the exact entity, give a significant boost
            shared = tokens_a & tokens_b & entity_set
            if shared:
                boost = max(boost, 0.4)
            else:
                boost = max(boost, 0.2)
                
    # Normalize score to max 1.0
    final_score = min(jaccard + boost, 1.0)
    return final_score

def main():
    # Load June 11 and June 12 events
    events_11_path = Path("outputs/events/2026-06-11_events.json")
    events_12_path = Path("outputs/events/2026-06-12_events.json")
    
    if not events_11_path.exists() or not events_12_path.exists():
        print("Events files not found. Please run the pipeline first.")
        return
        
    with open(events_11_path, "r") as f:
        events_11 = json.load(f)
        
    with open(events_12_path, "r") as f:
        events_12 = json.load(f)
        
    print(f"Loaded {len(events_11)} events from June 11 and {len(events_12)} events from June 12.")
    
    print("\n--- SIMILARITY MATRIX (IMPROVED) ---")
    for e2 in events_12:
        title2 = e2["title"]
        matches = []
        for e1 in events_11:
            title1 = e1["title"]
            score = improved_title_similarity(title1, title2)
            if score > 0.4:
                matches.append((title1, score))
        
        # Sort by score descending
        matches.sort(key=lambda x: x[1], reverse=True)
        if matches:
            print(f"\nJune 12: '{title2}'")
            for title1, score in matches[:3]:
                print(f"  -> June 11: '{title1}' (Score: {score:.3f})")

if __name__ == "__main__":
    main()

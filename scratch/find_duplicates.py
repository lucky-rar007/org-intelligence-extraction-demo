import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.similarity import title_similarity

def main():
    issues_path = Path("outputs/issues/issues.json")
    if not issues_path.exists():
        print("issues.json not found!")
        return
        
    with open(issues_path, "r", encoding="utf-8") as f:
        issues = json.load(f)
        
    # We want to find clusters of similar issues
    # Let's do a simple connected components or matching pairs group
    visited = set()
    clusters = []
    
    for i, issue1 in enumerate(issues):
        if issue1["id"] in visited:
            continue
            
        cluster = [issue1]
        visited.add(issue1["id"])
        
        for issue2 in issues[i+1:]:
            if issue2["id"] in visited:
                continue
                
            score = title_similarity(issue1["title"], issue2["title"])
            if score >= 0.45:  # threshold for similarity
                cluster.append(issue2)
                visited.add(issue2["id"])
                
        if len(cluster) > 1:
            clusters.append(cluster)
            
    print(f"Found {len(clusters)} clusters of potentially duplicate issues:")
    for idx, c in enumerate(clusters):
        print(f"\nCluster {idx + 1}:")
        for iss in c:
            print(f"  - [{iss['id']}] {iss['title']} (occurrence: {iss['occurrence_count']}, first_seen: {iss['first_seen'][:10]})")

if __name__ == "__main__":
    main()

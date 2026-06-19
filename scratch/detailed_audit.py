import json

def main():
    with open("outputs/issues/issues.json", "r") as f:
        issues = json.load(f)
        
    print(f"Total issues: {len(issues)}")
    for idx, iss in enumerate(issues):
        print(f"{idx+1}. [{iss['severity']}] {iss['title']} (Count: {iss['occurrence_count']}, Status: {iss['status']}, Date: {iss['first_seen'][:10]})")

if __name__ == "__main__":
    main()

"""Analyzes organizational dynamics, personnel bottlenecks, knowledge concentration, team health, and commitments."""

import logging
from datetime import datetime
from typing import List, Dict, Any

from domain.enums import CommitmentStatus, Severity, IssueStatus
from domain.models import Issue, Observation, Event, Commitment, Message
from storage.commitment_store import CommitmentStore

logger = logging.getLogger(__name__)


def normalize_name(name: str) -> str:
    """Standardize names to standard first names (e.g. Siddharth Rao -> Siddharth)."""
    if not name:
        return "Unknown"
    name_lower = name.lower()
    import config
    for kn in config.KNOWN_TEAM_NAMES:
        if kn.lower() in name_lower:
            return kn
    parts = name.strip().split()
    if parts:
        return parts[0].capitalize()
    return name.strip()


class OrgIntelligenceEngine:
    """Computes personnel risks, knowledge concentration, tracks commitments, and team health signals."""

    def __init__(self, commitment_store: CommitmentStore | None = None) -> None:
        """Initialize the OrgIntelligenceEngine."""
        self.commitment_store = commitment_store or CommitmentStore()

    def process_commitments(
        self,
        new_commitments: List[Commitment],
        messages: List[Message],
        report_date: str
    ) -> List[Commitment]:
        """Update existing commitments, merge new ones, and persist to storage.

        Args:
            new_commitments: List of new commitments extracted today.
            messages: Raw messages for today (used to check for completion).
            report_date: Current report date (YYYY-MM-DD).

        Returns:
            The complete list of all tracked commitments.
        """
        # Load historical commitments
        all_commitments = self.commitment_store.load_commitments()

        # Add new commitments (avoiding duplicates by description/owner/date)
        existing_keys = {(c.owner, c.description.lower(), c.created_date) for c in all_commitments}
        for nc in new_commitments:
            key = (nc.owner, nc.description.lower(), nc.created_date)
            if key not in existing_keys:
                all_commitments.append(nc)

        report_dt = datetime.strptime(report_date, "%Y-%m-%d").date()

        # Parse messages by sender (normalized first name)
        sender_messages = {}
        for m in messages:
            norm_sender = normalize_name(m.sender)
            sender_messages.setdefault(norm_sender, []).append(m.text.lower())

        # Define completion keywords
        completion_kws = ["done", "merged", "pr", "pushed", "fixed", "resolved", "completed", "working", "deployed", "pushed changes"]

        # Pre-compile the regex for word extraction and inline it
        import re
        word_re = re.compile(r"\b\w+\b")

        # Update all active commitments
        for c in all_commitments:
            if c.status == CommitmentStatus.COMPLETED:
                continue

            # Check if there is completion evidence in messages today
            owner_msgs = sender_messages.get(c.owner, [])
            # Extract keywords from commitment description to verify topic relevance
            desc_words = [w for w in word_re.findall(c.description.lower()) if len(w) > 3]
            
            completed = False
            for text in owner_msgs:
                # If message contains completion indicators
                if any(kw in text for kw in completion_kws):
                    # AND contains topic words or is clearly about the task
                    if not desc_words or any(w in text for w in desc_words):
                        completed = True
                        break

            if completed:
                c.status = CommitmentStatus.COMPLETED
                logger.info("Commitment '%s' by %s marked as COMPLETED on %s", c.description, c.owner, report_date)
            else:
                # Check if overdue
                due_dt = datetime.strptime(c.due_date, "%Y-%m-%d").date()
                if report_dt > due_dt:
                    c.status = CommitmentStatus.OVERDUE
                    logger.info("Commitment '%s' by %s marked as OVERDUE (due: %s, current: %s)", c.description, c.owner, c.due_date, report_date)
                else:
                    c.status = CommitmentStatus.OPEN

        self.commitment_store.save_commitments(all_commitments)
        return all_commitments

    def _load_all_events_map(self) -> Dict[str, Event]:
        from storage.event_store import EventStore
        event_store = EventStore()
        event_map = {}
        for file_path in event_store.output_dir.glob("*_events.json"):
            try:
                date_str = file_path.name.replace("_events.json", "")
                events = event_store.load_events(date_str)
                for e in events:
                    event_map[e.id] = e
            except Exception:
                pass
        return event_map

    def analyze_personnel_bottlenecks(self, issues: List[Issue]) -> Dict[str, Any]:
        """Detect engineers acting as dependency bottlenecks or single points of failure.

        Args:
            issues: All active and resolved issues.

        Returns:
            Dict containing bottlenecks list, dependency nodes list, and personnel risks findings.
        """
        event_map = self._load_all_events_map()
        person_stats = {}
        active_issues = [i for i in issues if i.status in (IssueStatus.OPEN, IssueStatus.MONITORING)]
        critical_active = [i for i in active_issues if i.severity in (Severity.HIGH, Severity.CRITICAL)]

        total_critical = len(critical_active)

        for issue in active_issues:
            # Extract participants from issues (we assume first name normalization)
            participants = set()
            for ev_id in issue.linked_event_ids:
                event = event_map.get(ev_id)
                if event and event.participants:
                    for p in event.participants:
                        participants.add(normalize_name(p))
            
            # (Text search fallback removed to fix bottleneck text-search: only count name mentions when name is in event.participants)
            
            if issue.affected_team:
                p_norm = normalize_name(issue.affected_team)
                import config
                if p_norm in config.KNOWN_TEAM_NAMES:
                    participants.add(p_norm)

            for p in participants:
                if p == "Unknown":
                    continue
                stats = person_stats.setdefault(p, {
                    "issues_involved": 0,
                    "critical_issues_involved": 0,
                    "resolved_issues": 0,
                    "ownership_count": 0
                })
                stats["issues_involved"] += 1
                if issue.severity in (Severity.HIGH, Severity.CRITICAL):
                    stats["critical_issues_involved"] += 1

        # Calculate bottlenecks and dependency nodes
        bottlenecks = []
        dependency_nodes = []
        people_risks = []

        for name, stats in person_stats.items():
            critical_involved = stats["critical_issues_involved"]
            pct = int((critical_involved / total_critical * 100)) if total_critical > 0 else 0

            # If involved in >= 30% of critical incidents or >= 2 total critical issues
            if pct >= 30 or critical_involved >= 2:
                bottlenecks.append(name)
                dependency_nodes.append(name)

                # Severity maps to concentration percentage
                sev = Severity.MEDIUM
                if pct >= 50:
                    sev = Severity.CRITICAL
                elif pct >= 30:
                    sev = Severity.HIGH

                finding = {
                    "person": name,
                    "concentration_percentage": pct,
                    "critical_issues_count": critical_involved,
                    "severity": sev.value,
                    "description": f"{name} is involved in {pct}% of delivery-critical incidents this week."
                }
                people_risks.append(finding)

        return {
            "top_bottlenecks": bottlenecks,
            "top_dependency_nodes": dependency_nodes,
            "people_risks": people_risks
        }

    def analyze_knowledge_concentration(self, issues: List[Issue]) -> Dict[str, Any]:
        """Detect technical silos and key-person knowledge concentration risks.

        Args:
            issues: All active and resolved issues.

        Returns:
            Dict containing knowledge concentration listings and risks.
        """
        event_map = self._load_all_events_map()
        # Map technical categories to issue counts and engineers involved
        tech_areas = {
            "Redis": ["redis"],
            "Deployment & Infrastructure": ["deployment", "infra", "build", "ci/cd", "ecr", "aws"],
            "Mobile (Android & iOS)": ["android", "ios", "mobile", "proguard", "app crash"],
            "Webhook & APIs": ["webhook", "api", "endpoint"],
            "Staging & Databases": ["database", "db", "staging", "connection pool", "sql"]
        }

        area_stats = {}
        for area in tech_areas:
            area_stats[area] = {"total_issues": 0, "engineer_counts": {}}

        active_issues = [i for i in issues if i.status in (IssueStatus.OPEN, IssueStatus.MONITORING)]

        for issue in active_issues:
            matched_areas = []
            title_lower = issue.title.lower()
            desc_lower = (issue.summary or "").lower()

            for area, keywords in tech_areas.items():
                if any(kw in title_lower or kw in desc_lower for kw in keywords):
                    matched_areas.append(area)

            # Detect participants
            participants = set()
            for ev_id in issue.linked_event_ids:
                event = event_map.get(ev_id)
                if event and event.participants:
                    for p in event.participants:
                        participants.add(normalize_name(p))

            import config
            for name in config.KNOWN_TEAM_NAMES:
                if name.lower() in title_lower or name.lower() in desc_lower:
                    participants.add(name)

            for area in matched_areas:
                area_stats[area]["total_issues"] += 1
                for p in participants:
                    if p == "Unknown":
                        continue
                    area_stats[area]["engineer_counts"][p] = area_stats[area]["engineer_counts"].get(p, 0) + 1

        knowledge_risks = []
        knowledge_concentration = []

        for area, stats in area_stats.items():
            total = stats["total_issues"]
            if total < 2:
                continue

            for engineer, count in stats["engineer_counts"].items():
                pct = int((count / total) * 100)
                # If one engineer handles >= 80% of issues in this subsystem
                if pct >= 80:
                    description = f"Deployment knowledge concentrated in one engineer ({engineer})." if "Deployment" in area else f"All {area} issues require {engineer}."
                    
                    risk = {
                        "subsystem": area,
                        "primary_engineer": engineer,
                        "concentration_percentage": pct,
                        "description": description,
                        "risks": ["Vacation risk", "Resignation risk", "Burnout risk", "Scaling risk"]
                    }
                    knowledge_risks.append(risk)
                    knowledge_concentration.append({
                        "subsystem": area,
                        "engineer": engineer,
                        "percentage": pct
                    })

        return {
            "knowledge_risks": knowledge_risks,
            "knowledge_concentration": knowledge_concentration
        }

    def analyze_team_health(
        self,
        events: List[Event],
        observations: List[Observation],
        commitments: List[Commitment]
    ) -> List[Dict[str, Any]]:
        """Evaluate team health signals (friction, ownership gap, silos, bottlenecks, execution risks).

        Args:
            events: Operational events today.
            observations: Historical/daily observations.
            commitments: All commitments.

        Returns:
            List of team health signals dictionaries.
        """
        signals = []
        
        # 1. PROCESS_FRICTION: standup reminders, timesheet requests, process compliance observations
        process_obs = [o for o in observations if "standup" in o.title.lower() or "reminder" in o.title.lower()]
        if len(process_obs) >= 2:
            signals.append({
                "signal_type": "PROCESS_FRICTION",
                "severity": Severity.MEDIUM.value,
                "description": f"Repeated reminders and process compliance friction detected ({len(process_obs)} sync reminders).",
                "evidence_count": len(process_obs)
            })

        # 2. OWNERSHIP_GAP: repeated ownership confusion
        ownership_obs = [o for o in observations if "owner" in o.title.lower() or "confusion" in o.title.lower() or "who is" in o.title.lower()]
        if ownership_obs:
            signals.append({
                "signal_type": "OWNERSHIP_GAP",
                "severity": Severity.HIGH.value,
                "description": "Unresolved ownership clarification questions causing team alignment delay.",
                "evidence_count": len(ownership_obs)
            })

        # 3. DELIVERY_RISK: release delays and blockers
        blocker_events = [e for e in events if e.severity in (Severity.HIGH, Severity.CRITICAL)]
        if len(blocker_events) >= 2:
            signals.append({
                "signal_type": "DELIVERY_RISK",
                "severity": Severity.HIGH.value,
                "description": f"Active delivery blockers are threatening release commitments (critical events: {len(blocker_events)}).",
                "evidence_count": len(blocker_events)
            })

        # 4. EXECUTION_RISK: missed/overdue commitments
        overdue = [c for c in commitments if c.status == CommitmentStatus.OVERDUE]
        if overdue:
            signals.append({
                "signal_type": "EXECUTION_RISK",
                "severity": Severity.HIGH.value,
                "description": f"Commitment completion rate is dropping, with {len(overdue)} overdue deliverables.",
                "evidence_count": len(overdue)
            })

        return signals

    def analyze_commitment_risks(self, commitments: List[Commitment]) -> List[Dict[str, Any]]:
        """Compute commitment risks and slippage trends."""
        total = len(commitments)
        completed = sum(1 for c in commitments if c.status == CommitmentStatus.COMPLETED)
        overdue = sum(1 for c in commitments if c.status == CommitmentStatus.OVERDUE)
        
        rate = int((completed / total * 100)) if total > 0 else 100
        
        risks = []
        if overdue > 0:
            risks.append({
                "risk_type": "OVERDUE_COMMITMENTS",
                "severity": Severity.HIGH.value,
                "description": f"Engineering commitments completion rate is {rate}%, with {overdue} commitments currently overdue.",
                "metrics": {"overdue_count": overdue, "completion_rate": rate}
            })
            
            # Check for client xyz specific slippage
            client_xyz_overdue = sum(1 for c in commitments if c.status == CommitmentStatus.OVERDUE and "client xyz" in c.description.lower())
            if client_xyz_overdue > 0:
                risks.append({
                    "risk_type": "CLIENT_XYZ_SLIPPAGE",
                    "severity": Severity.HIGH.value,
                    "description": f"Client XYZ commitments are slipping repeatedly with {client_xyz_overdue} overdue items.",
                    "metrics": {"client_xyz_overdue": client_xyz_overdue}
                })
        return risks





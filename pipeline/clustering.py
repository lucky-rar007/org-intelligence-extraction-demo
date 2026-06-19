"""Groups related issues into high-level root-cause clusters automatically with advanced metrics and trend tracking."""

import logging
import datetime
from datetime import timezone
from typing import List, Dict, Any

from domain.enums import IssueStatus, Severity
from domain.models import Issue, IssueCluster, Event
from storage.cluster_store import ClusterStore
from pipeline.org_intelligence import normalize_name

logger = logging.getLogger(__name__)

from config import CLUSTER_KEYWORD_MAPPINGS
CLUSTER_MAPPINGS = CLUSTER_KEYWORD_MAPPINGS


class ClusteringEngine:
    """Groups issues into root cause IssueClusters based on shared clients and components."""

    def __init__(self, cluster_store: ClusterStore | None = None) -> None:
        """Initialize the ClusteringEngine."""
        self.cluster_store = cluster_store or ClusterStore()

    def _load_all_events_map(self) -> Dict[str, Event]:
        """Load all events across days to trace evidence."""
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

    def cluster_issues(self, issues: List[Issue], report_date: str = None) -> List[IssueCluster]:
        """Group all issues into high-level clusters and persist the result.

        Args:
            issues: List of all active and resolved issues.
            report_date: Current report date (YYYY-MM-DD).

        Returns:
            List of generated/updated IssueCluster objects.
        """
        if not report_date:
            report_date = datetime.date.today().isoformat()

        report_dt = datetime.datetime.strptime(report_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)

        if not issues:
            logger.info("No issues to cluster.")
            return []

        # Load existing master clusters for trend analysis
        existing_clusters = self.cluster_store.load_clusters()
        prev_clusters_map = {c.cluster_id: c for c in existing_clusters}

        # Load events map for supporting evidence
        event_map = self._load_all_events_map()

        # Step 1: Assign issues to categories
        category_to_issues = {}
        unclustered_issues = []

        for issue in issues:
            matched_cat = None
            title_lower = issue.title.lower()
            desc_lower = (issue.summary or "").lower()

            for cat_name, keywords in CLUSTER_MAPPINGS.items():
                if any(kw in title_lower or kw in desc_lower for kw in keywords):
                    matched_cat = cat_name
                    break

            if matched_cat:
                category_to_issues.setdefault(matched_cat, []).append(issue)
            else:
                unclustered_issues.append(issue)

        # Step 2: Build clusters for category matches
        clusters = []

        # We treat predefined categories first
        for cat_name, cat_issues in category_to_issues.items():
            cluster_id = f"cls-{cat_name.lower().replace(' ', '-')}"
            cluster_title = f"{cat_name} Rollout Problems" if "Client" not in cat_name else f"{cat_name} Deployment Issues"
            # Adjust title slightly to sound natural
            if cat_name == "Payment Gateway":
                cluster_title = "Payment Gateway Rollout Problems"
            elif cat_name == "Webhook Systems":
                cluster_title = "Webhook Integration Incidents"
            elif cat_name == "Redis Cache":
                cluster_title = "Redis Infrastructure Issues"
            elif cat_name == "Staging Database":
                cluster_title = "Staging Database Connection Problems"
            elif cat_name == "Android App":
                cluster_title = "Android Application Performance & Quality"
            elif cat_name == "iOS App":
                cluster_title = "iOS Application Rollout Issues"

            cluster = self._build_cluster_object(
                cluster_id=cluster_id,
                title=cluster_title,
                cat_name=cat_name,
                cat_issues=cat_issues,
                report_date=report_date,
                report_dt=report_dt,
                prev_clusters_map=prev_clusters_map,
                event_map=event_map
            )
            clusters.append(cluster)

        # Step 3: Handle unclustered issues as single-issue clusters
        for idx, u_issue in enumerate(unclustered_issues, 1):
            cluster_id = f"cls-{u_issue.id}"
            # Clean title
            from pipeline.issue_tracker import normalize_issue_title
            norm_title = normalize_issue_title(u_issue.title).title()
            cluster_title = f"{norm_title} Stability" if norm_title else f"{u_issue.title} Group"
            
            cluster = self._build_cluster_object(
                cluster_id=cluster_id,
                title=cluster_title,
                cat_name=u_issue.title,
                cat_issues=[u_issue],
                report_date=report_date,
                report_dt=report_dt,
                prev_clusters_map=prev_clusters_map,
                event_map=event_map
            )
            clusters.append(cluster)

        # Persist master clusters
        self.cluster_store.save_clusters(clusters)
        
        # Save snapshot
        self.cluster_store.save_daily_snapshot(clusters, report_date)

        logger.info("Clustered %d issues into %d root cause clusters.", len(issues), len(clusters))
        return clusters

    def _build_cluster_object(
        self,
        cluster_id: str,
        title: str,
        cat_name: str,
        cat_issues: List[Issue],
        report_date: str,
        report_dt: datetime.datetime,
        prev_clusters_map: Dict[str, IssueCluster],
        event_map: Dict[str, Event]
    ) -> IssueCluster:
        """Helper to build an IssueCluster with all child details."""
        # 1. Supporting IDs
        related_ids = [i.id for i in cat_issues]
        supporting_event_ids = []
        for i in cat_issues:
            supporting_event_ids.extend(i.linked_event_ids)
        supporting_event_ids = list(set(supporting_event_ids))

        # 2. First / Last seen
        first_seen = min(i.first_seen for i in cat_issues)
        last_seen = max(i.last_seen for i in cat_issues)

        # 3. Status Rule (Filter to active issues only for status/severity)
        active_child_issues = [i for i in cat_issues if i.status in (IssueStatus.OPEN, IssueStatus.MONITORING)]

        if any(i.status == IssueStatus.OPEN for i in active_child_issues):
            status = IssueStatus.OPEN
        elif any(i.status == IssueStatus.MONITORING for i in active_child_issues):
            status = IssueStatus.MONITORING
        else:
            status = IssueStatus.RESOLVED

        # 4. Severity Rule: max(child severities of active issues)
        severity_order = [Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]
        highest_sev = Severity.LOW
        for i in active_child_issues:
            if severity_order.index(i.severity) > severity_order.index(highest_sev):
                highest_sev = i.severity

        # 5. Days open: report_date - earliest issue first_seen
        days_open = max(0, (report_dt.date() - first_seen.date()).days)

        # 6. Occurrence Count: child counts + recurring appearances
        occurrence_count = sum(i.occurrence_count for i in cat_issues)

        # 7. Timeline: Merged & sorted chronologically
        timeline_entries = []
        seen_timeline = set()
        for issue in cat_issues:
            for te in getattr(issue, "timeline_events", []):
                key = (te.get("date"), te.get("event"), te.get("reason", te.get("description", "")))
                if key not in seen_timeline:
                    seen_timeline.add(key)
                    timeline_entries.append({
                        "date": te.get("date", report_date),
                        "event": te.get("event", "UPDATE"),
                        "title": te.get("title", issue.title),
                        "description": te.get("description", te.get("reason", issue.summary or ""))
                    })
        try:
            timeline_entries.sort(key=lambda x: x["date"])
        except Exception:
            pass

        # 8. Business Area
        title_lower = title.lower()
        if "payment" in title_lower or "gateway" in title_lower or "paytm" in title_lower:
            business_area = "Finance / Checkout"
        elif "webhook" in title_lower:
            business_area = "Integrations"
        elif "redis" in title_lower:
            business_area = "Infrastructure / Caching"
        elif "database" in title_lower or "staging db" in title_lower:
            business_area = "Database / Testing"
        elif "android" in title_lower or "ios" in title_lower or "mobile" in title_lower:
            business_area = "Mobile Client"
        elif "client" in title_lower:
            business_area = "Client Relations / Delivery"
        else:
            business_area = "General Engineering"

        # 9. Risk Type
        # DELIVERY_RISK, CUSTOMER_RISK, REVENUE_RISK, TEAM_RISK, INFRASTRUCTURE_RISK, EXECUTION_RISK, STRATEGIC_RISK, QUALITY_RISK
        if "payment" in title_lower or "checkout" in title_lower:
            risk_type = "REVENUE_RISK"
        elif "client" in title_lower:
            risk_type = "CUSTOMER_RISK"
        elif "android" in title_lower or "ios" in title_lower or "mobile" in title_lower:
            risk_type = "QUALITY_RISK"
        elif "redis" in title_lower or "database" in title_lower or "db" in title_lower:
            risk_type = "INFRASTRUCTURE_RISK"
        elif "delivery" in title_lower or "release" in title_lower or "build" in title_lower:
            risk_type = "DELIVERY_RISK"
        else:
            if highest_sev in (Severity.HIGH, Severity.CRITICAL):
                risk_type = "EXECUTION_RISK"
            else:
                risk_type = "QUALITY_RISK"

        # 10. Recommended Action
        if "payment" in title_lower:
            rec_action = "Review release process and deployment ownership for the payment gateway integrations."
        elif "redis" in title_lower:
            rec_action = "Assign secondary Redis owner and complete knowledge transfer to mitigate single-point-of-failure risk."
        elif "client abc" in title_lower:
            rec_action = "Escalate ABC integration milestone review and rebalance delivery resources."
        elif "client xyz" in title_lower:
            rec_action = "Conduct technical sync with Client XYZ team to address custom transitions and mockups."
        elif "webhook" in title_lower:
            rec_action = "Audit webhook duplicate handler retry policies and QA queue load bounds."
        elif "database" in title_lower:
            rec_action = "Tune staging connection pool limits and check long-running queries."
        elif "android" in title_lower or "ios" in title_lower:
            rec_action = "Optimize Proguard setup and analyze mobile crash stacktraces to resolve scaling issues."
        else:
            rec_action = f"Review technical ownership of {title} and schedule incident root-cause analysis."

        # 11. Owner Candidates
        owner_candidates = set()
        for ev_id in supporting_event_ids:
            event = event_map.get(ev_id)
            if event and event.participants:
                for p in event.participants:
                    owner_candidates.add(normalize_name(p))
        # Text search fallback
        from config import KNOWN_TEAM_NAMES
        for name in KNOWN_TEAM_NAMES:
            if any(name.lower() in i.title.lower() or name.lower() in (i.summary or "").lower() for i in cat_issues):
                owner_candidates.add(name)
        owner_candidates.discard("Unknown")
        owner_list = list(owner_candidates)
        if not owner_list:
            owner_list = ["Aditya", "Vikram"] # Default leads

        # 12. Channels / Teams
        source_channels = list({i.affected_channel for i in cat_issues if i.affected_channel})
        source_teams = list({i.affected_team for i in cat_issues if i.affected_team})
        if not source_channels:
            source_channels = []
        if not source_teams:
            source_teams = []

        # 13. Confidence Score
        conf_sum = 0.0
        conf_count = 0
        for ev_id in supporting_event_ids:
            event = event_map.get(ev_id)
            if event:
                conf_sum += event.confidence_score
                conf_count += 1
        confidence_score = conf_sum / conf_count if conf_count > 0 else 0.9

        # 14. Trend Detection
        # Compare current active count against historical state
        prev_cluster = prev_clusters_map.get(cluster_id)
        if not prev_cluster:
            trend = "NEW"
        else:
            if status == IssueStatus.RESOLVED:
                trend = "RESOLVED"
            elif len(related_ids) > len(prev_cluster.supporting_issue_ids):
                trend = "WORSENING"
            else:
                curr_active_count = sum(1 for i in cat_issues if i.status in (IssueStatus.OPEN, IssueStatus.MONITORING))
                # Count previous active issues by looking at the status of their issues
                # (if we load the current issue status, it shows their current status, but we can check if they resolved today)
                if curr_active_count == 0:
                    trend = "RESOLVED"
                elif curr_active_count < len(related_ids) and (prev_cluster.status == IssueStatus.OPEN and status == IssueStatus.MONITORING):
                    trend = "IMPROVING"
                elif any(i.status == IssueStatus.RESOLVED for i in cat_issues):
                    trend = "IMPROVING"
                else:
                    trend = "STABLE"

        # 15. Premium Summary Generation
        if len(cat_issues) == 1:
            summary = f"{title} has experienced a single active incident concerning '{cat_issues[0].title}' on {first_seen.strftime('%d %b')}. Underlying cause is being monitored."
        else:
            issue_list_str = ", ".join(f"'{i.title}'" for i in cat_issues[:3])
            if len(cat_issues) > 3:
                issue_list_str += f" and {len(cat_issues) - 3} other incidents"
            summary = f"{cat_name if 'Client' in cat_name or 'App' in cat_name else title} has experienced repeated operational friction ({issue_list_str}) across {occurrence_count} occurrences over {days_open + 1} days, threatening {risk_type.lower().replace('_', ' ')}."

        return IssueCluster(
            cluster_id=cluster_id,
            title=title,
            summary=summary,
            business_area=business_area,
            severity=highest_sev,
            status=status,
            days_open=days_open,
            first_seen=first_seen,
            last_seen=last_seen,
            occurrence_count=occurrence_count,
            supporting_issue_ids=related_ids,
            supporting_event_ids=supporting_event_ids,
            recommended_action=rec_action,
            owner_candidates=owner_list,
            trend=trend,
            risk_type=risk_type,
            source_channels=source_channels,
            source_teams=source_teams,
            confidence_score=confidence_score,
            timeline=timeline_entries
        )

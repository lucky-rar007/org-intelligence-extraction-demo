"""Groups related issues into high-level root-cause clusters automatically with advanced metrics, registries, and LLM discovery."""

import logging
import datetime
import re
from datetime import timezone
from typing import List, Dict, Any, Optional

from domain.enums import IssueStatus, Severity
from domain.models import Issue, IssueCluster, Event, ClusterDefinition, CandidateCluster
from storage.cluster_store import ClusterStore
from storage.cluster_registry import ClusterRegistry
from pipeline.org_intelligence import normalize_name
from utils.similarity import title_similarity, normalize_text
from llm.llm_client import LLMClient

logger = logging.getLogger(__name__)

from config import CLUSTER_KEYWORD_MAPPINGS
CLUSTER_MAPPINGS = CLUSTER_KEYWORD_MAPPINGS


class ClusteringEngine:
    """Groups issues into root cause IssueClusters based on registry matching and LLM discovery."""

    def __init__(
        self, 
        cluster_store: ClusterStore | None = None,
        cluster_registry: ClusterRegistry | None = None,
        llm_client: LLMClient | None = None
    ) -> None:
        """Initialize the ClusteringEngine."""
        self.cluster_store = cluster_store or ClusterStore()
        self.cluster_registry = cluster_registry or ClusterRegistry()
        self.llm_client = llm_client

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

    def _slugify(self, text: str) -> str:
        """Derive a slug for the cluster ID from its name."""
        if not text:
            return "unknown"
        text = text.lower().strip()
        text = re.sub(r"[^\w\s\-]", "", text)
        text = re.sub(r"[\s\-]+", "_", text)
        return text

    def _find_best_match(self, issue: Issue, definitions: list) -> tuple[Optional[Any], float]:
        """Compute match score against all definitions and return best match and score."""
        best_def = None
        best_score = 0.0

        for d in definitions:
            score = self._compute_match_score(issue, d)
            if score > best_score:
                best_score = score
                best_def = d

        return best_def, best_score

    def _compute_match_score(self, issue: Issue, definition: Any) -> float:
        """Calculate match score using title similarity, keyword overlaps, component, and examples."""
        # 1. Title similarity against cluster name
        name_sim = title_similarity(issue.title, definition.name)

        # 2. Max similarity against example titles
        example_sims = [
            title_similarity(issue.title, ex)
            for ex in definition.example_titles
        ]
        max_example_sim = max(example_sims) if example_sims else 0.0

        # 3. Keyword overlap
        keywords = [kw.lower() for kw in definition.keywords]
        issue_text = (issue.title + " " + (issue.summary or "")).lower()
        kw_match_count = sum(1 for kw in keywords if kw in issue_text)
        kw_overlap = kw_match_count / len(keywords) if keywords else 0.0

        # 4. Client overlap
        client_overlap = 0.0
        for client in ["abc", "xyz"]:
            if client in issue_text:
                if client in definition.name.lower() or any(client in kw for kw in keywords):
                    client_overlap = 1.0
                    break

        # 5. Component / affected areas overlap
        comp_overlap = 0.0
        if issue.affected_areas:
            affected_lower = [a.lower() for a in issue.affected_areas]
            desc_lower = definition.description.lower()
            name_lower = definition.name.lower()
            if any(a in name_lower or a in desc_lower or any(a in kw for kw in keywords) for a in affected_lower):
                comp_overlap = 1.0

        base_sim = max(name_sim, max_example_sim)

        # Weighted heuristic score
        score = 0.6 * base_sim + 0.2 * kw_overlap + 0.1 * client_overlap + 0.1 * comp_overlap

        # Title similarity boost
        if base_sim >= 0.75 and kw_overlap > 0.0:
            score = max(score, base_sim + 0.05)

        # Deterministic keyword match rule
        issue_title_tokens = set(normalize_text(issue.title).split())
        has_exact_keyword = False
        for kw in keywords:
            if " " not in kw:
                if kw in issue_title_tokens:
                    has_exact_keyword = True
                    break
            else:
                if re.search(r'\b' + re.escape(kw) + r'\b', issue.title.lower()):
                    has_exact_keyword = True
                    break

        if has_exact_keyword:
            score = max(score, 0.85)

        return min(score, 1.0)

    def cluster_issues(self, issues: List[Issue], report_date: str = None) -> List[IssueCluster]:
        """Group issues using hybrid matching against cluster registry and candidate DB, fallback to LLM.

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

        # Load registries
        registry = self.cluster_registry.load_registry()
        candidates = self.cluster_registry.load_candidates()

        reg_map = {r.cluster_type_id: r for r in registry}
        cand_map = {c.cluster_type_id: c for c in candidates}

        issues_by_cluster_id = {}
        matched_definitions = {}

        for issue in issues:
            matched_id = None

            # Step 3: Match against permanent registry
            best_reg, best_reg_score = self._find_best_match(issue, registry)
            if best_reg and best_reg_score >= 0.80:
                matched_id = best_reg.cluster_type_id
                matched_definitions[matched_id] = best_reg
                logger.info("Issue '%s' matched permanent cluster '%s' (score %.2f)", 
                            issue.title, best_reg.name, best_reg_score)

            # Match against candidates database
            if not matched_id:
                best_cand, best_cand_score = self._find_best_match(issue, candidates)
                if best_cand and best_cand_score >= 0.80:
                    matched_id = best_cand.cluster_type_id
                    matched_definitions[matched_id] = best_cand
                    logger.info("Issue '%s' matched candidate cluster '%s' (score %.2f)", 
                                issue.title, best_cand.name, best_cand_score)

                    # Update candidate counters and metadata
                    best_cand.supporting_issue_count += 1
                    if issue.title not in best_cand.example_titles:
                        best_cand.example_titles.append(issue.title)
                    best_cand.last_seen = report_date

                    # Step 6: Promotion logic
                    if best_cand.supporting_issue_count >= 2:
                        self.cluster_registry.promote_candidate(best_cand.cluster_type_id)
                        # Reload mappings after promotion
                        registry = self.cluster_registry.load_registry()
                        candidates = self.cluster_registry.load_candidates()
                        reg_map = {r.cluster_type_id: r for r in registry}
                        cand_map = {c.cluster_type_id: c for c in candidates}
                        matched_definitions[matched_id] = reg_map[matched_id]
                    else:
                        self.cluster_registry.add_candidate(best_cand)

            # Step 4: LLM Cluster Discovery
            if not matched_id:
                if self.llm_client:
                    # Construct variables for context
                    known_info = []
                    for r in registry:
                        known_info.append(f"- ID: {r.cluster_type_id}, Name: {r.name}, Keywords: {', '.join(r.keywords)}")
                    known_str = "\n".join(known_info) if known_info else "None"

                    try:
                        from llm.prompt_loader import PromptLoader
                        prompt_loader = PromptLoader()
                        prompt = prompt_loader.render_prompt(
                            prompt_name="cluster_discovery",
                            variables={
                                "known_clusters": known_str,
                                "issue_title": issue.title,
                                "issue_summary": issue.summary or "",
                                "issue_team": issue.affected_team or "Unknown",
                                "issue_areas": ", ".join(issue.affected_areas) if issue.affected_areas else "None"
                            }
                        )
                        from llm.response_parser import ResponseParser, ResponseParseError, ResponseValidationError
                        max_retries = 3
                        res_json = None
                        for attempt in range(1, max_retries + 1):
                            try:
                                logger.info("LLM cluster discovery for issue '%s' (attempt %d/%d)", issue.title, attempt, max_retries)
                                response_text = self.llm_client.generate(prompt)
                                res_json = ResponseParser().parse_json_response(response_text)
                                if not isinstance(res_json, dict):
                                    raise ResponseValidationError("Expected a JSON object from cluster discovery, got: " + str(type(res_json)))
                                break
                            except (ResponseParseError, ResponseValidationError) as e:
                                if attempt == max_retries:
                                    raise
                                logger.warning(
                                    "Validation failed for cluster discovery on issue '%s' (attempt %d/%d). Error: %s. Retrying...",
                                    issue.title, attempt, max_retries, str(e)
                                )

                        create_new = res_json.get("create_new_cluster", False)
                        confidence = res_json.get("confidence", 0.0)

                        if create_new and confidence >= 0.85:
                            cluster_name = res_json.get("cluster_name")
                            cluster_id_slug = self._slugify(cluster_name)
                            
                            parent_cluster = res_json.get("parent_cluster", "operational_risk")
                            risk_type = res_json.get("risk_type", "QUALITY_RISK")
                            description = res_json.get("description", issue.summary or "")
                            rec_action = res_json.get("recommended_action", f"Review technical ownership of {cluster_name} and schedule root-cause review.")
                            keywords = res_json.get("keywords", [])

                            # Derive business area based on parent taxonomy
                            bus_area_map = {
                                "revenue_risk": "Finance / Checkout",
                                "delivery_risk": "Software Delivery",
                                "people_risk": "Human Resources / Team",
                                "operational_risk": "Operations / Coordination",
                                "infrastructure_risk": "Infrastructure / Caching"
                            }
                            business_area = bus_area_map.get(parent_cluster, "General Engineering")

                            new_cand = CandidateCluster(
                                cluster_type_id=cluster_id_slug,
                                name=cluster_name,
                                description=description,
                                business_area=business_area,
                                risk_type=risk_type,
                                parent_cluster=parent_cluster,
                                recommended_action=rec_action,
                                keywords=keywords,
                                example_titles=[issue.title],
                                confidence=confidence,
                                first_seen=report_date,
                                last_seen=report_date,
                                supporting_issue_count=1,
                                promotion_status="CANDIDATE"
                            )

                            self.cluster_registry.add_candidate(new_cand)
                            # Reload candidates registry maps
                            candidates = self.cluster_registry.load_candidates()
                            cand_map = {c.cluster_type_id: c for c in candidates}

                            matched_id = cluster_id_slug
                            matched_definitions[matched_id] = new_cand
                            logger.info("Discovered new candidate cluster '%s' with confidence %.2f", 
                                        cluster_name, confidence)
                    except Exception as e:
                        logger.error("LLM cluster discovery failed for issue '%s': %s", issue.title, str(e))

                # Temporary fallback if LLM declined or failed - use issue.id directly for backward compatibility
                if not matched_id:
                    matched_id = issue.id
                    logger.info("Temporary clustering fallback for issue '%s'", issue.title)

            issues_by_cluster_id.setdefault(matched_id, []).append(issue)

        # Build IssueCluster objects
        clusters = []
        for cluster_id, cat_issues in issues_by_cluster_id.items():
            definition = None
            if cluster_id in reg_map:
                definition = reg_map[cluster_id]
            elif cluster_id in cand_map:
                definition = cand_map[cluster_id]
            elif cluster_id in matched_definitions:
                definition = matched_definitions[cluster_id]
            else:
                # Build temporary definition dynamically
                from pipeline.issue_tracker import normalize_issue_title
                norm_title = normalize_issue_title(cat_issues[0].title).title()
                definition = ClusterDefinition(
                    cluster_type_id=cluster_id,
                    name=f"{norm_title} Stability" if norm_title else f"{cat_issues[0].title} Group",
                    description=cat_issues[0].summary or "",
                    business_area=f"{cat_issues[0].affected_team or 'General'} Engineering",
                    risk_type="QUALITY_RISK",
                    parent_cluster="operational_risk",
                    recommended_action=f"Review technical ownership of {cat_issues[0].title} and schedule incident root-cause analysis.",
                    keywords=[],
                    example_titles=[i.title for i in cat_issues]
                )

            cluster = self._build_cluster_object(
                cluster_id=f"cls-{definition.cluster_type_id}",
                definition=definition,
                cat_issues=cat_issues,
                report_date=report_date,
                report_dt=report_dt,
                prev_clusters_map=prev_clusters_map,
                event_map=event_map
            )
            clusters.append(cluster)

        # Persist master clusters
        self.cluster_store.save_clusters(clusters)
        
        # Save daily snapshot
        self.cluster_store.save_daily_snapshot(clusters, report_date)

        logger.info("Clustered %d issues into %d root cause clusters.", len(issues), len(clusters))
        return clusters

    def _build_cluster_object(
        self,
        cluster_id: str,
        definition: Any,
        cat_issues: List[Issue],
        report_date: str,
        report_dt: datetime.datetime,
        prev_clusters_map: Dict[str, IssueCluster],
        event_map: Dict[str, Event]
    ) -> IssueCluster:
        """Helper to build an IssueCluster with all child details."""
        # 1. Step 8: Preserve Evidence Chain
        related_ids = [i.id for i in cat_issues]
        supporting_event_ids = []
        supporting_thread_ids = []

        for i in cat_issues:
            supporting_event_ids.extend(i.linked_event_ids)
        supporting_event_ids = list(set(supporting_event_ids))

        # Trace supporting event IDs back to their source thread IDs to preserve evidence chain
        for ev_id in supporting_event_ids:
            event = event_map.get(ev_id)
            if event and event.source_thread_id and event.source_thread_id != "unknown":
                supporting_thread_ids.append(event.source_thread_id)
        supporting_thread_ids = list(set(supporting_thread_ids))

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
        business_area = definition.business_area

        # 9. Risk Type
        risk_type = definition.risk_type

        # 10. Recommended Action
        rec_action = definition.recommended_action or f"Review technical ownership of {definition.name} and schedule root-cause review."

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

        # 14. Step 10: Trend Detection with Historical Learning
        prev_cluster = prev_clusters_map.get(cluster_id)
        trend_history = []
        if prev_cluster:
            trend_history = list(prev_cluster.trend_history) if getattr(prev_cluster, "trend_history", None) else []

        severity_rank = {
            Severity.LOW: 0,
            Severity.MEDIUM: 1,
            Severity.HIGH: 2,
            Severity.CRITICAL: 3,
        }

        if not prev_cluster:
            trend = "NEW"
        else:
            if status == IssueStatus.RESOLVED:
                trend = "RESOLVED"
            elif len(related_ids) > len(prev_cluster.supporting_issue_ids):
                # Number of supporting issues grew
                trend = "WORSENING"
            elif severity_rank[highest_sev] > severity_rank[prev_cluster.severity]:
                # Severity increased
                trend = "WORSENING"
            elif occurrence_count > prev_cluster.occurrence_count:
                # Recurrence increased
                trend = "GROWING"
            else:
                curr_active_count = len(active_child_issues)
                prev_active_count = len([i_id for i_id in prev_cluster.supporting_issue_ids]) # approximate
                if curr_active_count == 0:
                    trend = "RESOLVED"
                elif curr_active_count < prev_active_count:
                    trend = "IMPROVING"
                else:
                    trend = "STABLE"

        trend_history.append({"date": report_date, "trend": trend})

        # 15. Premium Summary Generation
        if len(cat_issues) == 1:
            summary = f"{definition.name} has experienced a single active incident concerning '{cat_issues[0].title}' on {first_seen.strftime('%d %b')}. Underlying cause is being monitored."
        else:
            issue_list_str = ", ".join(f"'{i.title}'" for i in cat_issues[:3])
            if len(cat_issues) > 3:
                issue_list_str += f" and {len(cat_issues) - 3} other incidents"
            summary = f"{definition.name} has experienced repeated operational friction ({issue_list_str}) across {occurrence_count} occurrences over {days_open + 1} days, threatening {risk_type.lower().replace('_', ' ')}."

        return IssueCluster(
            cluster_id=cluster_id,
            title=definition.name,
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
            supporting_thread_ids=supporting_thread_ids,
            recommended_action=rec_action,
            owner_candidates=owner_list,
            trend=trend,
            trend_history=trend_history,
            risk_type=risk_type,
            source_channels=source_channels,
            source_teams=source_teams,
            confidence_score=confidence_score,
            timeline=timeline_entries
        )

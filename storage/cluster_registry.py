"""Persists and retrieves cluster definitions in the registry and candidate database.

Enables dynamic schema evolution and automatic promotion of candidate clusters.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

from domain.models import ClusterDefinition, CandidateCluster
from utils.file_utils import ensure_directory, load_json, save_json
import config

logger = logging.getLogger(__name__)


class ClusterRegistry:
    """Manages the permanent cluster registry and candidate cluster database."""

    def __init__(self, output_dir: Path = config.CLUSTERS_OUTPUT_DIR) -> None:
        self.output_dir = output_dir
        ensure_directory(self.output_dir)
        self._registry_file = self.output_dir / "registry.json"
        self._candidates_file = self.output_dir / "candidates.json"
        self.seed_registry_if_empty()

    def load_registry(self) -> list[ClusterDefinition]:
        """Load permanent cluster definitions from the registry."""
        if not self._registry_file.exists():
            return []
        try:
            data = load_json(self._registry_file)
            return [ClusterDefinition.model_validate(item) for item in data]
        except Exception as e:
            logger.error("Failed to load registry: %s", str(e))
            return []

    def save_registry(self, registry: list[ClusterDefinition]) -> None:
        """Save permanent cluster definitions atomically."""
        data = [json.loads(c.model_dump_json()) for c in registry]
        tmp_file = self._registry_file.with_name(self._registry_file.name + ".tmp")
        save_json(tmp_file, data)
        os.replace(tmp_file, self._registry_file)
        logger.info("Saved %d definitions to registry", len(registry))

    def load_candidates(self) -> list[CandidateCluster]:
        """Load candidate cluster definitions from candidates.json."""
        if not self._candidates_file.exists():
            return []
        try:
            data = load_json(self._candidates_file)
            return [CandidateCluster.model_validate(item) for item in data]
        except Exception as e:
            logger.error("Failed to load candidates: %s", str(e))
            return []

    def save_candidates(self, candidates: list[CandidateCluster]) -> None:
        """Save candidate definitions atomically."""
        data = [json.loads(c.model_dump_json()) for c in candidates]
        tmp_file = self._candidates_file.with_name(self._candidates_file.name + ".tmp")
        save_json(tmp_file, data)
        os.replace(tmp_file, self._candidates_file)
        logger.info("Saved %d definitions to candidates", len(candidates))

    def add_candidate(self, candidate: CandidateCluster) -> None:
        """Add a new candidate or update an existing one."""
        candidates = self.load_candidates()
        # Check if candidate already exists
        for i, c in enumerate(candidates):
            if c.cluster_type_id == candidate.cluster_type_id:
                candidates[i] = candidate
                self.save_candidates(candidates)
                return
        candidates.append(candidate)
        self.save_candidates(candidates)

    def promote_candidate(self, cluster_type_id: str) -> None:
        """Promote a candidate cluster to the permanent registry."""
        candidates = self.load_candidates()
        candidate_to_promote = None
        remaining_candidates = []

        for c in candidates:
            if c.cluster_type_id == cluster_type_id:
                candidate_to_promote = c
            else:
                remaining_candidates.append(c)

        if not candidate_to_promote:
            logger.warning("Candidate %s not found for promotion", cluster_type_id)
            return

        candidate_to_promote.promotion_status = "PROMOTED"
        
        # Add to registry
        registry = self.load_registry()
        # Avoid duplicate registry IDs
        if not any(r.cluster_type_id == cluster_type_id for r in registry):
            new_reg = ClusterDefinition(
                cluster_type_id=candidate_to_promote.cluster_type_id,
                name=candidate_to_promote.name,
                description=candidate_to_promote.description,
                business_area=candidate_to_promote.business_area,
                risk_type=candidate_to_promote.risk_type,
                parent_cluster=candidate_to_promote.parent_cluster,
                recommended_action=candidate_to_promote.recommended_action,
                keywords=candidate_to_promote.keywords,
                example_titles=candidate_to_promote.example_titles
            )
            registry.append(new_reg)
            self.save_registry(registry)
            logger.info("Successfully promoted candidate %s to registry", cluster_type_id)

        # Save remaining candidates
        self.save_candidates(remaining_candidates)

    def seed_registry_if_empty(self) -> None:
        """Seed the registry with initial clusters if empty or missing."""
        if self._registry_file.exists():
            return

        logger.info("Seeding cluster registry with default known taxonomy clusters.")
        default_registry = [
            ClusterDefinition(
                cluster_type_id="payment_gateway",
                name="Payment Gateway Problems",
                description="Issues and failures related to payment gateways, checkout transaction flows, and Paytm integrations.",
                business_area="Finance / Checkout",
                risk_type="REVENUE_RISK",
                parent_cluster="revenue_risk",
                recommended_action="Review release process and deployment ownership for the payment gateway integrations.",
                keywords=["paytm", "payment", "checkout", "transaction", "gateway", "refund"],
                example_titles=["Payment Gateway main build failed", "Paytm SDK Integration Issue"]
            ),
            ClusterDefinition(
                cluster_type_id="client_abc",
                name="Client ABC Delivery Issues",
                description="Issues, deployment blockers, or feature request friction associated with Client ABC integrations.",
                business_area="Client Relations / Delivery",
                risk_type="CUSTOMER_RISK",
                parent_cluster="revenue_risk",
                recommended_action="Escalate ABC integration milestone review and rebalance delivery resources.",
                keywords=["abc", "client abc", "sync dashboard"],
                example_titles=["Client ABC sync dashboard issue", "Pagination Fix Deployment Delay"]
            ),
            ClusterDefinition(
                cluster_type_id="client_xyz",
                name="Client XYZ Delivery Issues",
                description="Issues, layout problems, or feature request friction associated with Client XYZ integrations.",
                business_area="Client Relations / Delivery",
                risk_type="CUSTOMER_RISK",
                parent_cluster="revenue_risk",
                recommended_action="Conduct technical sync with Client XYZ team to address custom transitions and mockups.",
                keywords=["xyz", "client xyz", "mockups"],
                example_titles=["Client XYZ reports feature delivery delay", "Backend Integration Delay"]
            ),
            ClusterDefinition(
                cluster_type_id="redis_cache",
                name="Redis Infrastructure",
                description="Issues involving Redis servers, connection pool limits, caching spikes, or memory evictions.",
                business_area="Infrastructure / Caching",
                risk_type="INFRASTRUCTURE_RISK",
                parent_cluster="delivery_risk",
                recommended_action="Assign secondary Redis owner and complete knowledge transfer to mitigate single-point-of-failure risk.",
                keywords=["redis", "cache", "eviction", "server memory"],
                example_titles=["Redis Cache connection interruption", "Cache eviction didn't trigger"]
            ),
            ClusterDefinition(
                cluster_type_id="staging_database",
                name="Staging Database Connection Problems",
                description="Issues involving the staging database connection pool, query execution latency, or migration script failures.",
                business_area="Database / Testing",
                risk_type="INFRASTRUCTURE_RISK",
                parent_cluster="infrastructure_risk",
                recommended_action="Tune staging connection pool limits and check long-running queries.",
                keywords=["staging database", "staging db", "connection pool", "migration", "lock wait"],
                example_titles=["Staging database connections issue", "Composite Index Migration Script Deployment"]
            ),
            ClusterDefinition(
                cluster_type_id="android_app",
                name="Android Application Performance & Quality",
                description="Problems, bugs, crash reports, and build configuration issues on the Android mobile client.",
                business_area="Mobile Client",
                risk_type="QUALITY_RISK",
                parent_cluster="delivery_risk",
                recommended_action="Optimize Proguard setup and analyze mobile crash stacktraces to resolve scaling issues.",
                keywords=["android app", "android", "proguard", "mobile", "simulator", "font scaling"],
                example_titles=["Android Login Issue", "Google Play Console crash logs"]
            ),
            ClusterDefinition(
                cluster_type_id="ios_app",
                name="iOS Application Rollout Issues",
                description="Problems, build failures, and provisioning profile issues on the iOS mobile client.",
                business_area="Mobile Client",
                risk_type="QUALITY_RISK",
                parent_cluster="delivery_risk",
                recommended_action="Optimize Proguard setup and analyze mobile crash stacktraces to resolve scaling issues.",
                keywords=["ios app", "ios", "app store", "swift", "provisioning"],
                example_titles=["iOS Build Failure", "iOS provision profile expired"]
            ),
            ClusterDefinition(
                cluster_type_id="webhook_systems",
                name="Webhook Integration Incidents",
                description="Bugs and errors caused by webhook retries, payload processing, duplicate handlers, or response timeouts.",
                business_area="Integrations",
                risk_type="INFRASTRUCTURE_RISK",
                parent_cluster="infrastructure_risk",
                recommended_action="Audit webhook duplicate handler retry policies and QA queue load bounds.",
                keywords=["webhook", "payload", "duplicate", "payloads"],
                example_titles=["Webhook Duplicate Payloads Causing Errors"]
            )
        ]
        self.save_registry(default_registry)

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from psr_mcp.domain.errors import DomainError
from psr_mcp.domain.identity import (
    Membership,
    MembershipStatus,
    Organization,
    OrganizationStatus,
    Role,
)


def test_organization_and_membership_normalize_values() -> None:
    organization = Organization(
        id=" org-a ",
        name=" 기관 A ",
        status=OrganizationStatus.ACTIVE,
        created_at=datetime(2026, 7, 16, tzinfo=UTC),
    )
    membership = Membership(
        organization_id=organization.id,
        subject_id=" user-a ",
        roles=frozenset({Role.RESEARCHER}),
        project_ids=frozenset({" project-a1 "}),
        status=MembershipStatus.ACTIVE,
    )

    assert organization.id == "org-a"
    assert organization.name == "기관 A"
    assert membership.subject_id == "user-a"
    assert membership.project_ids == frozenset({"project-a1"})


def test_membership_requires_a_role() -> None:
    with pytest.raises(DomainError):
        Membership(
            organization_id="org-a",
            subject_id="user-a",
            roles=frozenset(),
            project_ids=None,
        )

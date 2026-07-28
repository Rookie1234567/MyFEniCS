"""Evaluator-only public API for Task035e reference certification."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .contracts import ReferenceCampaign
from .convergence import (
    CertificationPolicy,
    ReferenceCertification,
    certify_reference_campaign,
)
from .package import SealedPackageReceipt, write_sealed_reference_package


@dataclass(frozen=True, slots=True)
class CertificationAndSealResult:
    """Evaluator result; never pass this object to the blind controller."""

    certification: ReferenceCertification
    receipt: SealedPackageReceipt


@dataclass(frozen=True, slots=True)
class ReferenceCertifier:
    """Certify h10/h7.5/h5 and write the hidden package atomically."""

    policy: CertificationPolicy = CertificationPolicy()

    def certify(
        self,
        campaign: ReferenceCampaign,
    ) -> ReferenceCertification:
        return certify_reference_campaign(campaign, policy=self.policy)

    def certify_and_seal(
        self,
        campaign: ReferenceCampaign,
        path: Path | str,
        *,
        seal_incomplete_evidence: bool = False,
        overwrite: bool = False,
    ) -> CertificationAndSealResult:
        """Certify then seal.

        By default an incomplete or failed campaign cannot produce a hidden
        reference package.  ``seal_incomplete_evidence`` is an explicit
        evaluator-side escape hatch for preserving a controlled-stop record;
        such a package remains marked unqualified and cannot satisfy Task035e.
        """

        certification = self.certify(campaign)
        receipt = write_sealed_reference_package(
            path,
            certification,
            require_qualified=not seal_incomplete_evidence,
            overwrite=overwrite,
        )
        return CertificationAndSealResult(
            certification=certification,
            receipt=receipt,
        )


def certify_reference(
    campaign: ReferenceCampaign,
    *,
    policy: CertificationPolicy = CertificationPolicy(),
) -> ReferenceCertification:
    """Functional evaluator API for an in-memory certification."""

    return ReferenceCertifier(policy=policy).certify(campaign)


__all__ = [
    "CertificationAndSealResult",
    "ReferenceCertifier",
    "certify_reference",
]

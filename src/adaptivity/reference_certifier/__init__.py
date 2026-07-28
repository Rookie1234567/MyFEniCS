"""Task035e evaluator-side hidden-reference certification.

The blind controller has no dependency on this package.  Only the reference
certifier and final hidden auditor may consume these contracts and packages.
"""

from .api import (
    CertificationAndSealResult,
    ReferenceCertifier,
    certify_reference,
)
from .contracts import (
    ASSEMBLY_MODE,
    ComplexObservation,
    ComplexValue,
    DiffractionOrderObservation,
    FIXED_ORDER_COUNT,
    FIXED_ORDER_M,
    FIXED_ORDER_N,
    FIXED_ORDER_PORTS,
    PhysicalRunIdentity,
    REQUIRED_TOTAL_SCALARS,
    ReferenceCampaign,
    ReferenceContractError,
    ReferenceRunResult,
    RunGateEvidence,
    ScalarObservation,
    fixed_order_inventory,
)
from .convergence import (
    CertificationGateSummary,
    CertificationPolicy,
    QUALIFIED,
    REFERENCE_CERTIFICATION_FAILED,
    REFERENCE_CERTIFICATION_INCOMPLETE,
    ReferenceCertification,
    ThreePointConvergence,
    analyze_three_point,
    certify_reference_campaign,
)
from .package import (
    SEALED_REFERENCE_PACKAGE_JSON_SCHEMA,
    SEALED_REFERENCE_PACKAGE_KIND,
    SEALED_REFERENCE_PACKAGE_SCHEMA,
    SealedPackageReceipt,
    SealedReferencePackageError,
    build_sealed_reference_package,
    read_sealed_reference_package,
    validate_sealed_reference_package,
    write_sealed_reference_package,
)


__all__ = [
    "ASSEMBLY_MODE",
    "CertificationAndSealResult",
    "CertificationGateSummary",
    "CertificationPolicy",
    "ComplexObservation",
    "ComplexValue",
    "DiffractionOrderObservation",
    "FIXED_ORDER_COUNT",
    "FIXED_ORDER_M",
    "FIXED_ORDER_N",
    "FIXED_ORDER_PORTS",
    "PhysicalRunIdentity",
    "QUALIFIED",
    "REFERENCE_CERTIFICATION_FAILED",
    "REFERENCE_CERTIFICATION_INCOMPLETE",
    "REQUIRED_TOTAL_SCALARS",
    "ReferenceCampaign",
    "ReferenceCertification",
    "ReferenceCertifier",
    "ReferenceContractError",
    "ReferenceRunResult",
    "RunGateEvidence",
    "SEALED_REFERENCE_PACKAGE_JSON_SCHEMA",
    "SEALED_REFERENCE_PACKAGE_KIND",
    "SEALED_REFERENCE_PACKAGE_SCHEMA",
    "ScalarObservation",
    "SealedPackageReceipt",
    "SealedReferencePackageError",
    "ThreePointConvergence",
    "analyze_three_point",
    "build_sealed_reference_package",
    "certify_reference",
    "certify_reference_campaign",
    "fixed_order_inventory",
    "read_sealed_reference_package",
    "validate_sealed_reference_package",
    "write_sealed_reference_package",
]

"""Optional, provenance-preserving external-system adapters."""

from adversary_pursuit.integrations.contracts import (
    ExternalReference,
    IntegrationRecord,
    QueryReceipt,
)
from adversary_pursuit.integrations.local_tool import LocalToolReceipt
from adversary_pursuit.integrations.nucleotide import (
    NucleotideFingerprintPreview,
    NucleotideLookupPreview,
)
from adversary_pursuit.integrations.roast import RoastDecodePreview

__all__ = [
    "ExternalReference",
    "IntegrationRecord",
    "LocalToolReceipt",
    "NucleotideFingerprintPreview",
    "NucleotideLookupPreview",
    "QueryReceipt",
    "RoastDecodePreview",
]

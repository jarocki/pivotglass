"""Optional, provenance-preserving external-system adapters."""

from pivotglass.integrations.contracts import (
    ExternalReference,
    IntegrationRecord,
    QueryReceipt,
)
from pivotglass.integrations.local_tool import LocalToolReceipt
from pivotglass.integrations.nucleotide import (
    NucleotideFingerprintComparison,
    NucleotideFingerprintPreview,
    NucleotideLookupPreview,
)
from pivotglass.integrations.roast import RoastDecodePreview
from pivotglass.integrations.scot_execution import (
    ScotPublicationJournal,
    ScotPublicationReceipt,
)
from pivotglass.integrations.scot_publication import ScotWritePlan
from pivotglass.integrations.synapse_execution import (
    SynapseShadowJournal,
    SynapseShadowReceipt,
)
from pivotglass.integrations.synapse_migration import SynapseMigrationPlan
from pivotglass.integrations.synapse_model_deployment import (
    SynapseModelDeploymentJournal,
    SynapseModelDeploymentPlan,
    SynapseModelDeploymentReceipt,
)

__all__ = [
    "ExternalReference",
    "IntegrationRecord",
    "LocalToolReceipt",
    "NucleotideFingerprintComparison",
    "NucleotideFingerprintPreview",
    "NucleotideLookupPreview",
    "QueryReceipt",
    "RoastDecodePreview",
    "ScotWritePlan",
    "ScotPublicationJournal",
    "ScotPublicationReceipt",
    "SynapseMigrationPlan",
    "SynapseModelDeploymentJournal",
    "SynapseModelDeploymentPlan",
    "SynapseModelDeploymentReceipt",
    "SynapseShadowJournal",
    "SynapseShadowReceipt",
]

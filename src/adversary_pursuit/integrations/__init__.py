"""Optional, provenance-preserving external-system adapters."""

from adversary_pursuit.integrations.contracts import (
    ExternalReference,
    IntegrationRecord,
    QueryReceipt,
)
from adversary_pursuit.integrations.local_tool import LocalToolReceipt
from adversary_pursuit.integrations.nucleotide import (
    NucleotideFingerprintComparison,
    NucleotideFingerprintPreview,
    NucleotideLookupPreview,
)
from adversary_pursuit.integrations.roast import RoastDecodePreview
from adversary_pursuit.integrations.scot_execution import (
    ScotPublicationJournal,
    ScotPublicationReceipt,
)
from adversary_pursuit.integrations.scot_publication import ScotWritePlan
from adversary_pursuit.integrations.synapse_execution import (
    SynapseShadowJournal,
    SynapseShadowReceipt,
)
from adversary_pursuit.integrations.synapse_migration import SynapseMigrationPlan
from adversary_pursuit.integrations.synapse_model_deployment import (
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

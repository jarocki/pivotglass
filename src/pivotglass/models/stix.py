"""STIX 2.1 abstraction layer.

Thin helper functions over python-stix2 that hide strict validation from module
authors. Module authors call helpers; the library handles validation.

@decision DEC-STIX-001
@title Thin helper functions over python-stix2, not a custom STIX implementation
@status accepted
@rationale python-stix2 provides full STIX 2.1 compliance including deterministic
           content-based IDs for SCOs. Our helpers are convenience wrappers that
           provide sensible defaults and handle common patterns (SCO creation,
           relationship linking). Wrapping rather than re-implementing avoids
           duplicating STIX spec logic and ensures spec compliance automatically.

@decision DEC-STIX-002
@title dict_to_stix returns original dict for unrecognized types
@status accepted
@rationale Modules may return custom STIX extensions or future SCO types not yet
           in this helper layer. Returning the original dict (instead of raising)
           lets store_stix_objects decide what to do with unrecognized objects,
           keeping the helper layer non-breaking as the module ecosystem grows.
"""

from __future__ import annotations

import uuid

from stix2 import (
    URL,
    Bundle,
    DomainName,
    EmailAddress,
    File,
    IPv4Address,
    IPv6Address,
    Relationship,
    Vulnerability,
)

# Namespace for deterministic vulnerability ids (see create_vulnerability).
_VULNERABILITY_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_OID, "pivotglass/stix/vulnerability")


def create_ipv4(value: str, **kwargs) -> IPv4Address:
    """Create a STIX IPv4Address SCO.

    Parameters
    ----------
    value:
        The IPv4 address string (e.g. "1.2.3.4").
    **kwargs:
        Additional STIX SCO properties passed to python-stix2.

    Returns
    -------
    IPv4Address
        A python-stix2 IPv4Address object with a deterministic content-based ID.
    """
    return IPv4Address(value=value, **kwargs)


def create_ipv6(value: str, **kwargs) -> IPv6Address:
    """Create a STIX IPv6Address SCO.

    Parameters
    ----------
    value:
        The IPv6 address string (e.g. "::1").
    **kwargs:
        Additional STIX SCO properties passed to python-stix2.
    """
    return IPv6Address(value=value, **kwargs)


def create_domain(value: str, **kwargs) -> DomainName:
    """Create a STIX DomainName SCO.

    Parameters
    ----------
    value:
        The domain name string (e.g. "example.com").
    **kwargs:
        Additional STIX SCO properties passed to python-stix2.
    """
    return DomainName(value=value, **kwargs)


def create_url(value: str, **kwargs) -> URL:
    """Create a STIX URL SCO.

    Parameters
    ----------
    value:
        The URL string (e.g. "https://example.com/path").
    **kwargs:
        Additional STIX SCO properties passed to python-stix2.
    """
    return URL(value=value, **kwargs)


def create_email(value: str, **kwargs) -> EmailAddress:
    """Create a STIX EmailAddress SCO.

    Parameters
    ----------
    value:
        The email address string (e.g. "user@example.com").
    **kwargs:
        Additional STIX SCO properties passed to python-stix2.
    """
    return EmailAddress(value=value, **kwargs)


def create_file(value: str = "", **kwargs) -> File:
    """Create a file SCO while retaining the analyst-facing hash value.

    Modules that know several hashes for one file (MalwareBazaar, hashlookup)
    pass ``hashes``; it is merged with the hash implied by *value* rather than
    colliding with it. Without *value*, the strongest supplied hash becomes the
    analyst-facing value.
    """
    length_to_algorithm = {32: "MD5", 40: "SHA-1", 64: "SHA-256"}
    hashes = dict(kwargs.pop("hashes", None) or {})
    if value:
        hashes.setdefault(length_to_algorithm.get(len(value), "SHA-256"), value)
    else:
        value = next((hashes[key] for key in ("SHA-256", "SHA-1", "MD5") if hashes.get(key)), "")
        value = value or next(iter(hashes.values()), "")
    return File(
        hashes=hashes,
        x_indicator_value=value,
        allow_custom=True,
        **kwargs,
    )


def create_vulnerability(**kwargs) -> Vulnerability:
    """Create a STIX Vulnerability SDO whose id is derived from its CVE name.

    SDO ids are random by default, so the same CVE reported by three modules (or
    by two runs of one module) would become unrelated objects. A UUIDv5 over the
    upper-cased name makes the id a function of the CVE: every module that reports
    CVE-2024-0001 addresses the same object, which the workspace then deduplicates
    by id exactly as it does for SCOs (DEC-WS-004, DEC-WORKSPACE-VULNERABILITY-001).
    STIX 2.1 permits any UUID version in an SDO id.
    """
    name = str(kwargs.get("name", "")).strip().upper()
    if not name:
        raise ValueError("a vulnerability needs a name (the CVE identifier)")
    kwargs["name"] = name
    kwargs.setdefault("id", f"vulnerability--{uuid.uuid5(_VULNERABILITY_NAMESPACE, name)}")
    return Vulnerability(allow_custom=True, **kwargs)


def create_relationship(
    source_ref: str,
    target_ref: str,
    relationship_type: str,
) -> Relationship:
    """Create a STIX Relationship SRO.

    Parameters
    ----------
    source_ref:
        STIX ID of the source object.
    target_ref:
        STIX ID of the target object.
    relationship_type:
        STIX relationship type string (e.g. "resolves-to", "communicates-with").

    Returns
    -------
    Relationship
        A python-stix2 Relationship object with a random UUID-based ID.
    """
    return Relationship(
        relationship_type=relationship_type,
        source_ref=source_ref,
        target_ref=target_ref,
    )


def create_bundle(objects: list) -> Bundle:
    """Create a STIX Bundle from a list of STIX objects.

    Parameters
    ----------
    objects:
        List of python-stix2 objects (SCOs, SDOs, SROs).

    Returns
    -------
    Bundle
        A python-stix2 Bundle with a random UUID-based ID.
    """
    return Bundle(objects=objects)


# Mapping from STIX type string to helper function
_SCO_CREATORS: dict[str, object] = {
    "ipv4-addr": create_ipv4,
    "ipv6-addr": create_ipv6,
    "domain-name": create_domain,
    "url": create_url,
    "email-addr": create_email,
    "file": create_file,
}


# @decision DEC-NEIGHBOUR-RELATIONSHIP-001
# @title A neighbour a source reports is stored as an explicit relationship
# @status accepted
# @rationale Modules name the object a neighbour belongs to in an ``x_*_of``
#            field (an IP that a domain resolves to, a domain's nameserver, the
#            AS that announces an IP). A field holds one value and an existing
#            object keeps its first fields, so an IP shared by two domains, or
#            already in the workspace, lost the link: the shared-infrastructure
#            case pivots exist for. At store time each such field becomes a
#            STIX relationship with a deterministic id (carrier -> named
#            object), many-to-many and deduplicated. The source that reported it
#            is the provenance; it is a reported relation, not an inference.
NEIGHBOUR_FIELDS: dict[str, str] = {
    "x_rdap_nameserver_of": "nameserver-of",
    "x_mnemonic_pdns_resolution_of": "resolution-of",
    "x_dns_resolution_of": "resolution-of",
    "x_dns_nameserver_of": "nameserver-of",
    "x_dns_mail_exchanger_of": "mail-exchanger-of",
    "x_dns_alias_of": "alias-of",
    "x_asn_of": "announces",
    "x_internetdb_hostname_of": "hostname-of",
}
_NEIGHBOUR_NAMESPACE = uuid.UUID("2f7d8c1e-5b8a-5c43-9d1e-4a6b0c9e7f21")


def neighbour_relationship_id(source_ref: str, verb: str, target_ref: str) -> str:
    return f"relationship--{uuid.uuid5(_NEIGHBOUR_NAMESPACE, f'{source_ref}|{verb}|{target_ref}')}"


def dict_to_stix(d: dict):
    """Convert a plain dict (from module hunt()) to a STIX object.

    Handles the common SCO types returned by built-in modules:
    - {"type": "ipv4-addr", "value": "1.2.3.4"}
    - {"type": "ipv6-addr", "value": "::1"}
    - {"type": "domain-name", "value": "example.com"}
    - {"type": "url", "value": "https://example.com"}
    - {"type": "email-addr", "value": "user@example.com"}
    - {"type": "vulnerability", "name": "CVE-2024-0001", ...} (an SDO, see create_vulnerability)

    Parameters
    ----------
    d:
        Dict with at minimum a "type" and "value" key. Extra keys are
        forwarded to the python-stix2 constructor as keyword arguments.

    Returns
    -------
    stix2 SCO object | dict
        The STIX object if the type is recognized; the original dict otherwise.
        See DEC-STIX-002 for rationale on returning the original dict.
    """
    stix_type = d.get("type", "")
    if stix_type == "vulnerability":
        # An SDO: named, not valued, and with no "value" to split off.
        return create_vulnerability(**{k: v for k, v in d.items() if k != "type"})
    creator = _SCO_CREATORS.get(stix_type)
    if creator is None:
        return d  # unrecognized type -- pass through unchanged (DEC-STIX-002)
    value = d.get("value", "")
    extra = {k: v for k, v in d.items() if k not in ("type", "value")}
    # allow_custom=True permits x_ prefixed extension fields (e.g. x_creation_date,
    # x_org) returned by whois_lookup and similar modules without raising
    # ExtraPropertiesError from python-stix2.
    if stix_type == "file":
        return creator(value, **extra)
    return creator(value, allow_custom=True, **extra)

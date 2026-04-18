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

from stix2 import (
    IPv4Address,
    IPv6Address,
    DomainName,
    URL,
    EmailAddress,
    Relationship,
    Bundle,
)


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
}


def dict_to_stix(d: dict):
    """Convert a plain dict (from module hunt()) to a STIX object.

    Handles the common SCO types returned by built-in modules:
    - {"type": "ipv4-addr", "value": "1.2.3.4"}
    - {"type": "ipv6-addr", "value": "::1"}
    - {"type": "domain-name", "value": "example.com"}
    - {"type": "url", "value": "https://example.com"}
    - {"type": "email-addr", "value": "user@example.com"}

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
    creator = _SCO_CREATORS.get(stix_type)
    if creator is None:
        return d  # unrecognized type -- pass through unchanged (DEC-STIX-002)
    value = d.get("value", "")
    extra = {k: v for k, v in d.items() if k not in ("type", "value")}
    # allow_custom=True permits x_ prefixed extension fields (e.g. x_creation_date,
    # x_org) returned by whois_lookup and similar modules without raising
    # ExtraPropertiesError from python-stix2.
    return creator(value, allow_custom=True, **extra)

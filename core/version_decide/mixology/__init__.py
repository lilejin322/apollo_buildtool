"""adapted from pipgrip: https://github.com/ddelange/pipgrip"""
import pkg_resources
import re

from typing import cast, NewType

__version__ = "0.2.1"

NormalizedName = NewType("NormalizedName", str)
_canonicalize_regex = re.compile(r"[-_.]+")


def canonicalize_name(name: str) -> NormalizedName:
    """ This is taken from PEP 503."""
    value = _canonicalize_regex.sub("-", name).lower()
    return cast(NormalizedName, value)


def parse_req(requirement, extras=None):
    """parse request"""
    if requirement == "_root_" or requirement == "." or requirement.startswith(".["):
        req = pkg_resources.Requirement.parse(
            requirement.replace(".", "rubbish", 1)
            if requirement.startswith(".[")
            else "rubbish"
        )
        if extras is not None:
            req.extras = extras
        req.key = "." if requirement.startswith(".[") else requirement
        full_str = req.__str__().replace(req.name, req.key)
        req.name = req.key
    else:
        req = pkg_resources.Requirement.parse(requirement)
        if extras is not None:
            req.extras = extras
        req.key = canonicalize_name(req.key)
        req.name = req.key
        full_str = req.__str__() 
    
    def __str__():
        return full_str

    req.__str__ = __str__
    req.extras_name = (
        req.name + "[" + ",".join(req.extras) + "]" if req.extras else req.name
    )
    req.extras = frozenset(req.extras)
    return req

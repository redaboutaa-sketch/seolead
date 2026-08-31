"""YAML, stripped of its 1.1 folklore.

Measured on 2026-08-31, in one line of default PyYAML:

    a: YES        -> True                (the bug a real lead carries in its
    b: 0123       -> 83   (octal!)        qualification: battery_interest=true)
    c: 2026-08-31 -> datetime.date       (a version string becomes a date)
    d: 12:30      -> 750  (sexagesimal!) (an opening-hours value becomes 750)
    e: Off        -> False

Every one of these is a silent type change: the file says one thing, the loader
hands the application another, no test sees it because the test reads the same
loader. The pydantic guard on boolean option values catches ONE shape of this
after the fact; this loader removes the whole class at the source.

`strict_load` resolves:
    - booleans for the canonical spellings ONLY: `true` / `false` (lowercase);
    - integers without the octal reading — a leading zero stays a string;
    - floats and null as usual.
It resolves NOTHING ELSE implicitly: YES/No/on/Off are strings, dates are
strings (the configs type their dates as str on purpose — a reviewer reads what
was written), sexagesimals are strings.

Configuration files are the only intended users. Data from providers is parsed
by their own schemas, not by this.
"""
from __future__ import annotations

import re

import yaml


class StrictConfigLoader(yaml.SafeLoader):
    """SafeLoader minus every implicit resolver the 1.1 spec regrets."""


# Drop ALL implicit resolvers, then re-add only the unambiguous ones.
StrictConfigLoader.yaml_implicit_resolvers = {}

StrictConfigLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool", re.compile(r"^(?:true|false)$"), list("tf"))
StrictConfigLoader.add_implicit_resolver(
    "tag:yaml.org,2002:null", re.compile(r"^(?:~|null|Null|NULL|)$"),
    ["~", "n", "N", ""])
# Integers: decimal only, no leading zero (which 1.1 read as octal). `0` itself
# stays an int.
StrictConfigLoader.add_implicit_resolver(
    "tag:yaml.org,2002:int", re.compile(r"^-?(?:0|[1-9]\d*)$"),
    list("-0123456789"))
StrictConfigLoader.add_implicit_resolver(
    "tag:yaml.org,2002:float",
    re.compile(r"^-?(?:0|[1-9]\d*)\.\d+$"), list("-0123456789"))


def strict_load(text: str):
    """`yaml.load` with the strict loader. The one entry point."""
    return yaml.load(text, Loader=StrictConfigLoader)

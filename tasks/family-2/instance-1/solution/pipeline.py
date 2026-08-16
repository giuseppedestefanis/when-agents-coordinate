"""Reference implementation of `pipeline.summarise_transactions`.

Compose the four step functions in chain order. The agents'
deliverable is this file plus the four step modules; the
reference produces the same five files.
"""

from __future__ import annotations

from parse import parse
from validate import validate
from aggregate import aggregate
from format_output import format_output


def summarise_transactions(records):
    return format_output(aggregate(validate(parse(records))))

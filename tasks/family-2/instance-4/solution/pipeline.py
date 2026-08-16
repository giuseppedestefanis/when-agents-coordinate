"""Reference implementation of `pipeline.summarise_transactions_v2`.

Same composition shape as Instance 1, with the v2 task name and
the v2 output type.
"""

from __future__ import annotations

from parse import parse
from validate import validate
from aggregate import aggregate
from format_output import format_output


def summarise_transactions_v2(records):
    return format_output(aggregate(validate(parse(records))))

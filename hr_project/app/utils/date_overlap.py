"""Generic date-range overlap detection, reusable across any entity that has
a start date and an optional end date (NULL end date = still ongoing /
open-ended, treated as "infinity" for overlap purposes).

Used by: EmploymentRecord (İş yerləri), InsurancePolicy (Sığorta), and any
future entity with the same start/end shape.
"""


def dates_overlap(start1, end1, start2, end2):
    """True if the two [start, end] ranges overlap. A None end means that
    range is still open (ongoing), which overlaps with anything at or
    after its start."""
    if start1 is None or start2 is None:
        return False
    if end1 is None and end2 is None:
        return True
    if end1 is None:
        return end2 >= start1
    if end2 is None:
        return end1 >= start2
    return start1 <= end2 and start2 <= end1


def find_overlapping(records, new_start, new_end, exclude_id=None,
                      start_attr="date_from", end_attr="date_to"):
    """Scans `records` (any iterable of model instances with the given
    start/end attribute names) and returns the first one whose date range
    overlaps [new_start, new_end], or None if there's no conflict."""
    for r in records:
        if exclude_id is not None and getattr(r, "id", None) == exclude_id:
            continue
        r_start = getattr(r, start_attr)
        r_end = getattr(r, end_attr)
        if dates_overlap(new_start, new_end, r_start, r_end):
            return r
    return None

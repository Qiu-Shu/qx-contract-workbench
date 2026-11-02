"""Shared source-order fence for both personal Weixin execution paths."""


def ordered_commands(commands, first_batches, *, is_stop, is_resume):
    """Return (event id, payload) pairs, or None when a restart order is unknown.

    Complete, unique upstream orders must agree. Without them only an original
    response batch establishes relative order; receiving a message later does not.
    """
    orders = []
    for field in ('source_sequence', 'source_created_ms'):
        values = [getattr(value, field) for _, value in commands]
        if values and all(value is not None for value in values) and len(set(values)) == len(values):
            orders.append(sorted(commands, key=lambda item: getattr(item[1], field)))
    if orders:
        if any([key for key, _ in order] != [key for key, _ in orders[0]] for order in orders[1:]):
            return None
        return orders[0]
    batches, stopped = first_batches(), None
    for key, value in commands:
        if stopped is not None and is_resume(value):
            if batches.get(key) is None or batches.get(key) != batches.get(stopped):
                return None
            stopped = None
        if is_stop(value):
            stopped = key
    return commands

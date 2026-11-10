"""Pure date predicates: no fetching, today's date or synthetic legal approval."""
from datetime import date


def effective_on(authority,event_date):
    """Inclusive last applicable day; unknown start/date fails closed.

    This checks an explicit source window, not whether the text is verified law.
    A null end means no recorded end, and is usable only after separate review.
    """
    if type(event_date) is not date or authority.effective_from is None:
        return False
    return authority.effective_from <= event_date and (
        authority.effective_to is None or event_date <= authority.effective_to)

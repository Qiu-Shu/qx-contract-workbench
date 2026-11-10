"""Local OCR remains deliberately unavailable until models and policy are approved."""


def unavailable(page_number):
    # No model download, network, subprocess, or guessed text is allowed here.
    return f'page:{page_number}:unsupported', f'OCR_NOT_DEPLOYED:page:{page_number}'

"""Local, best-effort forensic copy of a model reply that failed candidate parsing.

Why this module exists
----------------------
A material reply can be rejected after the provider has already been paid for it:
the envelope is valid, the JSON is valid, but the candidate structure is not
accepted. The durable receipt keeps only a fixed rejection category
(``rejection_reason``), which by design never contains model text, so there is
nothing left to diagnose from. Without a copy of the *content* the only way to
improve the prompt is guesswork.

This module stores exactly one artifact per distinct rejected content: the
message content string, byte for byte, in a plain ``.txt`` file next to the
workspace database. It is a forensic aid, not a product feature:

* **Strictly local.** Nothing here opens a socket, writes to the database or
  touches the installation directory. The only effect is one file in a
  directory the operator already owns.
* **Never changes a rejection.** Every failure path inside :func:`save` and
  :func:`save_response` is swallowed and reported as one warning. A full disk,
  a read-only directory or an unexpected payload shape must never turn a
  rejected reply into a crash, and must never change the reply or its error
  code.
* **Idempotent.** The file name is derived from the content digest, so the same
  content rejected twice produces one file.
* **Bounded.** At most ``MAX_BYTES`` of content is kept; the rest is replaced by
  the ``[truncated]`` marker line so a reader can tell the copy is incomplete.

Location
--------
The directory is ``<workspace>/rejected-responses`` -- a sibling of
``workbench.db`` -- because that is the one place the operator already knows how
to find and already treats as private. The workspace root is bound explicitly by
:func:`configure` from the single entry point that opens a workspace. When no
root is bound (tests, acceptance tools, a bare transport probe) the module falls
back to a directory under the system temporary directory and logs the real path
once, so the operator is never left guessing where the file went.
"""
import hashlib
import json
import logging
import os
from pathlib import Path
import tempfile

from ..ops.file_paths import filesystem_path

_logger = logging.getLogger(__name__)

DIRECTORY_NAME = 'rejected-responses'
ENVIRONMENT_VARIABLE = 'CN_CONTRACT_REJECTED_RESPONSES_DIR'
FILE_PREFIX = 'rejected-response-'
SUFFIX = '.txt'
DIGEST_CHARS = 16
MAX_BYTES = 1024 * 1024
TRUNCATED = '\n[truncated]\n'

# Bound workspace root; ``None`` means "resolve from the fallback chain".
_root = None
# The resolved fallback directory is logged once, not on every rejection.
_reported = set()


def configure(root):
    """Bind the archive to a workspace root, or ``None`` to restore the fallback.

    Args:
        root: The workspace directory that contains ``workbench.db``, or ``None``.
            A ``str`` is accepted for native callers.

    Returns:
        None.
    """
    global _root
    _root = None if root is None else Path(root)


def directory():
    """Return the directory rejected contents are written to.

    Returns:
        ``<configured workspace>/rejected-responses`` when a workspace root is
        bound, else ``$CN_CONTRACT_REJECTED_RESPONSES_DIR`` when that variable
        names a path, else ``<system temp>/cn-contract-rejected-responses``.
    """
    if _root is not None:
        return filesystem_path(_root) / DIRECTORY_NAME
    override = os.environ.get(ENVIRONMENT_VARIABLE, '')
    if override:
        return filesystem_path(override)
    return filesystem_path(Path(tempfile.gettempdir()) / ('cn-contract-' + DIRECTORY_NAME))


def content_of(raw):
    """Extract ``choices[0].message.content`` from a raw provider body.

    Args:
        raw: The complete provider response body as ``str`` or ``bytes``.

    Returns:
        The message content string, or ``''`` when the body is not a completion
        this module can read. Extraction never raises: it runs on the failure
        path, where a second exception would replace the real rejection.
    """
    try:
        value = json.loads(raw)
        content = value['choices'][0]['message']['content']
    except (ValueError, KeyError, IndexError, TypeError):
        return ''
    return content if type(content) is str else ''


def save_response(raw):
    """Store the content of a raw provider body, best effort.

    Args:
        raw: The complete provider response body as ``str`` or ``bytes``.

    Returns:
        The written (or already existing) path, or ``None`` when the content was
        unreadable or could not be written.
    """
    return save(content_of(raw))


def save(content):
    """Store one rejected content string, best effort and once per digest.

    Args:
        content: The model message content. Anything but a non-empty ``str`` is
            ignored.

    Returns:
        The path of the stored copy, or ``None`` when nothing was written.
    """
    if type(content) is not str or not content:
        return None
    try:
        target = directory() / (FILE_PREFIX + _digest(content) + SUFFIX)
        if target.exists():
            return target
        target.parent.mkdir(parents=True, exist_ok=True)
        _report_once(target.parent)
        # Write then rename: a crash mid-write cannot leave a half file that a
        # later identical rejection would mistake for a complete copy.
        temporary = target.with_name(target.name + '.part-' + _digest(content)[:8])
        temporary.write_bytes(_bounded(content))
        os.replace(temporary, target)
        return target
    except Exception as error:
        # Never let diagnostics change the outcome of the reply under rejection: a
        # full disk, a read-only directory or an unexpected payload is reported once
        # and then ignored. The line stays inside the closed
        # ``model_response_rejected stage=...`` token family, because material
        # rejection diagnostics must remain one vocabulary and carry no model text,
        # no path and no exception message -- only a fixed kind.
        _logger.warning('model_response_rejected stage=archive failed kind=%s',
            'os' if isinstance(error, OSError) else 'other')
        return None


def _digest(content):
    """Return the first ``DIGEST_CHARS`` of the content's SHA-256, in lowercase.

    Args:
        content: The model message content.

    Returns:
        A 16 character lowercase hexadecimal digest.
    """
    return hashlib.sha256(content.encode('utf-8', 'surrogatepass')).hexdigest()[:DIGEST_CHARS]


def _bounded(content):
    """Encode ``content`` as UTF-8, keeping at most ``MAX_BYTES`` and marking a cut.

    Args:
        content: The model message content.

    Returns:
        The bytes to write. A cut payload is decoded back on a whole-character
        boundary and ends with the ``TRUNCATED`` marker line.
    """
    payload = content.encode('utf-8', 'surrogatepass')
    if len(payload) <= MAX_BYTES:
        return payload
    kept = payload[:MAX_BYTES].decode('utf-8', 'ignore')
    return (kept + TRUNCATED).encode('utf-8', 'surrogatepass')


def _report_once(path):
    """Log the directory actually in use the first time this process writes.

    Args:
        path: The directory the archive is writing to.

    Returns:
        None.
    """
    key = str(path)
    if key in _reported:
        return
    _reported.add(key)
    # INFO, not WARNING: material rejection warnings are a single
    # ``model_response_rejected stage=...`` family of closed tokens, and a path
    # line at WARNING level would break that. This is diagnostic context only.
    _logger.info('model_response_archive_dir path=%s', key)

"""Conversation-authorized local reads, with no run or model side effects.

Internal only: a future HTTP/runner entry must resolve citation IDs from a
server-held receipt rather than accept caller-authored CitationRef snapshots.
"""
import sqlite3

from ... import domain as d
from ...security import ServiceError
from .. import service


def _check(actor, call, database):
    with database.session() as db:
        row = service._owned(actor, call.expected_scope.conversation_id, db)
        service._expected(row, call)


def execute_tool(actor, call, database, adapter):
    try:
        call = d.AssistantLibraryToolCall.model_validate(
            call.model_dump(mode='python', warnings=False) if isinstance(call, d.AssistantLibraryToolCall) else call)
    except (ValueError, TypeError):
        raise ServiceError('LIBRARY_TOOL_INPUT_INVALID', 422) from None
    _check(actor, call, database)
    try:
        # Release the business DB transaction while reading the separate library.
        if call.tool == 'legal_library.search':
            result = d.AssistantLibraryToolResult(tool=call.tool, scope=call.expected_scope,
                page=d.LibraryCitationPage.model_validate(adapter.search(call.query).model_dump(mode='python', warnings=False)))
        else:
            result = d.AssistantLibraryToolResult(tool=call.tool, scope=call.expected_scope,
                citation=d.CitationRef.model_validate(adapter.read_original(call.citation).model_dump(mode='python', warnings=False)))
    except (ValueError, TypeError, OSError, sqlite3.Error) as error:
        _check(actor, call, database)
        code = str(error)
        if type(error) is not ValueError or code not in {
                'LIBRARY_QUERY_INVALID', 'LIBRARY_NOT_CONFIGURED', 'LIBRARY_GENERATION_STALE',
                'LIBRARY_SOURCE_UNAVAILABLE', 'LIBRARY_CITATION_INVALID', 'LIBRARY_CITATION_MISMATCH'}:
            code = 'LIBRARY_SOURCE_UNAVAILABLE'
        raise ServiceError(code, 422 if code.endswith('INVALID') else 409) from None
    _check(actor, call, database)
    return result

"""Material input is source-bound data, never a tool plan or implicit consent."""
from uuid import uuid4
import pytest
from cn_contract import domain as d
from cn_contract.assistant.material_codec import validate_candidate


def test_material_candidate_requires_known_source():
    candidate = d.MainMaterialCandidate(text='待核结论', citations=('a' * 64,))
    with pytest.raises(ValueError):
        validate_candidate(candidate, ())


def test_material_candidate_cannot_request_tools():
    with pytest.raises(ValueError):
        d.MainMaterialCandidate.model_validate({'text':'候选', 'citations':[], 'tool_plan':{'calls':[]}})


def test_material_selection_rejects_browser_body_and_paths():
    with pytest.raises(ValueError):
        d.MainMaterialSelection.model_validate({'request_id':str(uuid4()), 'content':'外加正文', 'path':'C:/secret'})

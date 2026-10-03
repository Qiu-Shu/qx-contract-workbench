"""T12 scoped staged candidate detection uses conspicuously fictional canaries."""
from tests.helpers.synthetic_operations import feature


def test_synthetic_canary_candidate_blocks_release():
    scan = feature('secrets', 'scan_candidates')
    canary = ('SYNTHETIC_'+'SECRET_DO_NOT_USE_'+'unit-test-only-1234567890').encode()
    result = scan({'candidate.env': b'QCC_API_KEY='+canary+b'\n'})
    assert not result.ok and result.findings and all(canary.decode() not in f.reason for f in result.findings)


def test_clean_metadata_is_not_secret():
    scan = feature('secrets', 'scan_candidates')
    result = scan({'manifest.json': b'{"key_ref":"server-reference-only","synthetic_only":true}'})
    assert result.ok and result.findings == ()


def test_real_git_index_canary_detected_even_when_working_file_clean(tmp_path):
    import subprocess
    scan = feature('secrets', 'scan_staged')
    root = tmp_path/'repository'; root.mkdir()
    subprocess.run(['git', 'init', str(root)], check=True, capture_output=True)
    canary = ('SYNTHETIC_'+'SECRET_DO_NOT_USE_'+'staged-only-1234567890').encode()
    candidate = root/'candidate.env'; candidate.write_bytes(b'QCC_API_KEY='+canary)
    subprocess.run(['git', '-C', str(root), 'add', 'candidate.env'], check=True, capture_output=True)
    candidate.write_bytes(b'key_ref=server-reference-only')
    result = scan(root)
    assert not result.ok and result.checked_files == 1
    assert canary.decode() not in result.model_dump_json()


def test_public_metadata_and_placeholder_do_not_grant_secret_exemption():
    scan = feature('secrets', 'scan_candidates')
    canary = ('SYNTHETIC_'+'SECRET_DO_NOT_USE_'+'artifact-1234567890').encode()
    assert not scan({'artifact.metadata.json': b'{"value":"'+canary+b'"}'}).ok
    assert scan({'candidate.env': b'QCC_API_KEY=${SERVER_KEY_REFERENCE}\n'}).ok


def test_compressed_docx_metadata_canary_is_scanned():
    from io import BytesIO
    from zipfile import ZipFile, ZIP_DEFLATED
    canary = ('SYNTHETIC_'+'SECRET_DO_NOT_USE_'+'compressed-metadata-1234567890').encode()
    out = BytesIO()
    with ZipFile(out, 'w', compression=ZIP_DEFLATED) as archive:
        archive.writestr('docProps/custom.xml', b'<metadata>'+canary+b'</metadata>')
    result = feature('secrets', 'scan_candidates')({'derived.docx': out.getvalue()})
    assert not result.ok and canary.decode() not in result.model_dump_json()


def test_virtual_secret_filename_is_not_reflected_in_findings():
    canary = ('SYNTHETIC_'+'SECRET_DO_NOT_USE_'+'filename-1234567890').encode()
    result = feature('secrets', 'scan_candidates')({canary.decode()+'.env': canary})
    assert not result.ok and canary.decode() not in result.model_dump_json()


def test_filename_only_virtual_secret_blocks_candidate():
    canary = 'SYNTHETIC_'+'SECRET_DO_NOT_USE_'+'filename-only-1234567890'
    result = feature('secrets', 'scan_candidates')({canary+'.json': b'{"synthetic":true}'})
    assert not result.ok and canary not in result.model_dump_json()

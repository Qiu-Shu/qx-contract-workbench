"""Independent imaginary PDFs and actual server boundaries; no OCR/live calls."""
from datetime import datetime, timezone
from decimal import Decimal
from io import BytesIO
from uuid import uuid4

import pytest

from cn_contract.config import load_settings
from cn_contract.documents import ingest, parse_document
from cn_contract.documents.pdf_adapter import parse_pdf
from cn_contract.domain import (CalculationInput, CoverageId, Fact, FactDecision, FactSnapshot,
    PolicySnapshot, ReviewContext, SafeExpression, UploadMeta)
from cn_contract.facts.calculate import calculate_expression, payment_base_facts
from cn_contract.facts.confirm import confirm_facts
from cn_contract.facts.extract import build_fact_candidates
from cn_contract.facts.storage import initialize_storage
from cn_contract.review.model_adapter import MockProvider, model_configuration
from cn_contract.review.workflow import current_manifest, prompt_configuration, run_review
from cn_contract.security import ServiceError
from tests.helpers.synthetic_documents import pdf, world


VISIBLE = b'BT /F1 12 Tf 72 720 Td (SYNTHETIC Buyer owes CNY 13750.) Tj ET\n'
SECOND = b'BT /F1 12 Tf 72 680 Td (SYNTHETIC Hidden CNY 999999.) Tj ET\n'


def visual_pdf(content, *, crop=None, gs=None, image=False):
    """One page with independent literal resources and a valid xref."""
    resources = b'/Font << /F1 3 0 R >>'
    if gs is not None:
        resources += b' /ExtGState << /GS1 ' + gs + b' >>'
    if image:
        resources += b' /XObject << /Im1 6 0 R >>'
    crop_entry = b'' if crop is None else b' /CropBox [' + crop + b']'
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [4 0 R] /Count 1 >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]' + crop_entry +
        b' /Resources << ' + resources + b' >> /Contents 5 0 R >>',
        b'<< /Length ' + str(len(content)).encode() + b' >>\nstream\n' + content + b'\nendstream']
    if image:
        objects.append(b'<< /Type /XObject /Subtype /Image /Width 1 /Height 1 '
            b'/ColorSpace /DeviceGray /BitsPerComponent 8 /Length 1 >>\nstream\n\xff\nendstream')
    output = bytearray(b'%PDF-1.4\n')
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(str(number).encode() + b' 0 obj\n' + obj + b'\nendobj\n')
    start = len(output)
    output.extend(b'xref\n0 ' + str(len(offsets)).encode() + b'\n0000000000 65535 f \n')
    for offset in offsets[1:]:
        output.extend(f'{offset:010d} 00000 n \n'.encode())
    output.extend(f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n'.encode())
    return bytes(output)


RISKS = [
    ('white', VISIBLE + b'1 g\n' + SECOND, {}, 'PDF_TEXT_COLOR_REQUIRES_CONFIRMATION'),
    ('transparent', VISIBLE + b'/GS1 gs\n' + SECOND, {'gs': b'<< /ca 0 /CA 0 >>'}, 'PDF_TRANSPARENCY_REQUIRES_CONFIRMATION'),
    ('partial_alpha', VISIBLE + b'/GS1 gs\n' + SECOND, {'gs': b'<< /ca 0.25 >>'}, 'PDF_TRANSPARENCY_REQUIRES_CONFIRMATION'),
    ('opaque_cover', VISIBLE + SECOND + b'1 g 70 675 230 18 re f\n', {}, 'PDF_TEXT_OCCLUSION_REQUIRES_CONFIRMATION'),
    ('black_background', b'0 g 70 675 230 18 re f\n' + VISIBLE + SECOND, {}, 'PDF_TEXT_BACKGROUND_REQUIRES_CONFIRMATION'),
    ('stroke_cover', VISIBLE + SECOND + b'1 G 20 w 70 686 m 300 686 l S\n', {}, 'PDF_TEXT_OCCLUSION_REQUIRES_CONFIRMATION'),
    ('outside_right', VISIBLE + SECOND.replace(b'72 680', b'720 680'), {}, 'PDF_TEXT_OUTSIDE_VISIBLE_PAGE'),
    ('cropbox', VISIBLE + SECOND, {'crop': b'0 700 612 792'}, 'PDF_TEXT_OUTSIDE_VISIBLE_PAGE'),
    ('render_mode', VISIBLE + b'3 Tr\n' + SECOND, {}, 'TEXT_RENDERING_REQUIRES_CONFIRMATION'),
    ('clip', b'0 700 612 92 re W n\n' + VISIBLE + SECOND, {}, 'PDF_DRAWING_EFFECT_REQUIRES_CONFIRMATION'),
    ('blend', VISIBLE + b'/GS1 gs\n' + SECOND, {'gs': b'<< /BM /Multiply >>'}, 'PDF_DRAWING_EFFECT_REQUIRES_CONFIRMATION'),
    ('image_conflict', VISIBLE + b'q 230 0 0 18 70 675 cm /Im1 Do Q\n' + SECOND, {'image': True}, 'VISIBLE_IMAGE_TEXT_NOT_VERIFIED'),
]


@pytest.mark.parametrize('name,content,kwargs,reason', RISKS, ids=[r[0] for r in RISKS])
def test_risky_pdf_page_keeps_candidate_anchors_but_requires_visual_check(name, content, kwargs, reason):
    parsed = parse_pdf(visual_pdf(content, **kwargs), uuid4(), load_settings())
    assert parsed.parts == ('page:1:manual',)
    assert f'{reason}:page:1' in parsed.quality_issues
    assert parsed.anchors and '13750' in parsed.anchors[0].quote and '999999' in parsed.anchors[0].quote


@pytest.mark.parametrize('content', [VISIBLE, b'1 g 60 665 260 80 re f 0 g\n' + VISIBLE + SECOND,
    VISIBLE + b'0 g 60 665 260 80 re S\n', VISIBLE + b'1 g 400 50 100 30 re f\n'])
def test_black_text_and_ordinary_borders_remain_read(content):
    parsed = parse_pdf(visual_pdf(content), uuid4(), load_settings())
    assert parsed.parts == ('page:1:read',)
    assert parsed.quality_issues == () and parsed.unsupported_parts == ()


@pytest.mark.parametrize('name,content,kwargs', [
    ('black', VISIBLE + SECOND, {}),
    ('white', VISIBLE + b'1 g\n' + SECOND, {}),
    ('transparent', VISIBLE + b'/GS1 gs\n' + SECOND, {'gs': b'<< /ca 0 /CA 0 >>'}),
    ('covered', VISIBLE + SECOND + b'1 g 70 675 230 18 re f\n', {})])
def test_independent_synthetic_render_confirms_hidden_second_amount(name, content, kwargs):
    import pypdfium2
    with pypdfium2.PdfDocument(visual_pdf(content, **kwargs)) as document:
        page = document[0]
        bitmap = page.render(scale=1)
        image = bitmap.to_pil()
        try:
            pixels = list(image.crop((70, 97, 300, 117)).convert('RGB').get_flattened_data())
            assert sum(min(pixel) < 240 for pixel in pixels) > 0 if name == 'black' else not any(min(pixel) < 240 for pixel in pixels)
        finally:
            image.close()
            bitmap.close()
            page.close()


def persisted(tmp_path, data, *, legacy_confirmed=False, fact_specs=None):
    import cn_contract.persistence as p
    p, _, _, database, actor, matter = world(tmp_path)
    initialize_storage(database)
    with database.session() as db:
        version = ingest(BytesIO(data), UploadMeta(matter_id=matter.id, original_name='SYNTHETIC-VISIBILITY.pdf',
            mime='application/pdf', baseline_view=None, supersedes_id=None), actor, db=db)
        parsed = parse_document(version, None, actor=actor, db=db)
        specs = fact_specs or [('total_price', {'kind': 'decimal', 'value': '999999'}, 'CNY')]
        facts = build_fact_candidates(parsed, {'facts': [{'field': field,
            'typed_value': typed, 'unit': unit, 'provenance_type': 'document',
            'anchor_ids': [str(parsed.anchors[0].id)], 'receipt_ids': []} for field, typed, unit in specs]},
            matter_id=matter.id, version=1, actor=actor, db=db)
        if legacy_confirmed:
            facts = tuple(Fact(**{**f.model_dump(mode='python'), 'confirmation_status': 'confirmed',
                'confirmed_by': actor.user_id, 'confirmed_at': datetime.now(timezone.utc)}) for f in facts)
        snapshot = FactSnapshot(version=1, facts=tuple(facts), sha256=p.fact_snapshot_sha256(facts))
        p.save_fact_snapshot(matter.id, snapshot, actor, db)
    return p, database, actor, matter, version, parsed, snapshot


@pytest.mark.parametrize('decision', ['confirmed', 'corrected'])
def test_risky_document_fact_cannot_be_confirmed_or_corrected_as_original(tmp_path, decision):
    p, database, actor, matter, _, _, snapshot = persisted(tmp_path, visual_pdf(VISIBLE + b'1 g\n' + SECOND))
    fact = snapshot.facts[0]
    value = fact.typed_value if decision == 'confirmed' else {'kind': 'decimal', 'value': '13750'}
    with database.session() as db:
        with pytest.raises(ServiceError) as exc:
            confirm_facts(matter.id, 1, [FactDecision(fact_id=fact.id, decision=decision,
                confirmed_value=value, reason='SYNTHETIC claimed manual reading is not a visual verification record')], actor, db=db)
        assert exc.value.code == 'SOURCE_VISUAL_CONFIRMATION_REQUIRED'
        assert p.read_matter(matter.id, actor, db).active_fact_version == 1


def test_risky_candidate_can_be_rejected_without_asserting_original_visible(tmp_path):
    p, database, actor, matter, _, _, snapshot = persisted(tmp_path, visual_pdf(VISIBLE + b'1 g\n' + SECOND))
    fact = snapshot.facts[0]
    with database.session() as db:
        result = confirm_facts(matter.id, 1, [FactDecision(fact_id=fact.id, decision='rejected',
            confirmed_value=fact.typed_value, reason='SYNTHETIC amount not verified')], actor, db=db)
        assert result.facts[0].confirmation_status == 'rejected' and result.version == 2


def test_legacy_confirmed_risky_fact_is_blocked_before_calculation(tmp_path):
    _, database, actor, matter, _, _, snapshot = persisted(tmp_path, visual_pdf(VISIBLE + b'1 g\n' + SECOND), legacy_confirmed=True)
    fact = snapshot.facts[0]
    with database.session() as db, pytest.raises(ServiceError) as exc:
        calculate_expression(SafeExpression(ast={'kind': 'variable', 'name': 'amount'}, unit='CNY'),
            {'amount': Decimal('999999')}, inputs=(CalculationInput(name='amount', value='999999', unit='CNY', fact_ids=(fact.id,)),),
            matter_id=matter.id, actor=actor, db=db)
    assert exc.value.code == 'SOURCE_VISUAL_CONFIRMATION_REQUIRED'


def review_context(p, database, actor, matter, version, snapshot):
    from cn_contract.authorities.storage import initialize_storage as authorities_init
    from cn_contract.rules.storage import initialize_storage as rules_init, policy_sha256
    from cn_contract.rules.loader import save_policy, register_default_cards, read_rule_snapshot
    from cn_contract.review.storage import initialize_storage as review_init
    authorities_init(database)
    rules_init(database)
    review_init(database)
    with database.session() as db:
        register_default_cards(actor, matter_id=matter.id, db=db)
        policy = PolicySnapshot(client_ref=matter.client_ref, version=1, sha256=policy_sha256(matter.client_ref, 1, ()),
            preferences=(), approved_by=None, approved_at=None)
        save_policy(policy, actor, matter_id=matter.id, db=db)
        p.transition_matter(matter.id, 'ready_for_review', actor, db)
        current = p.read_matter(matter.id, actor, db)
        rules = read_rule_snapshot(actor, matter_id=matter.id, db=db)
        return ReviewContext(matter=current, document_versions=(version,), fact_snapshot=snapshot, position=current.position,
            rules=rules.rules, policy=policy, authority_ids=(), allowed_scope=tuple(CoverageId))


def test_legacy_confirmed_risky_fact_is_blocked_before_review(tmp_path):
    p, database, actor, matter, version, _, snapshot = persisted(tmp_path, visual_pdf(VISIBLE + b'1 g\n' + SECOND), legacy_confirmed=True)
    context = review_context(p, database, actor, matter, version, snapshot)
    with database.session() as db, pytest.raises(ServiceError) as exc:
        current_manifest(context, actor, db, prompt_configuration(model_configuration(MockProvider())))
    assert exc.value.code == 'SOURCE_VISUAL_CONFIRMATION_REQUIRED'


def test_rejected_risk_page_cannot_supply_review_citations(tmp_path):
    p, database, actor, matter, version, parsed, snapshot = persisted(tmp_path, visual_pdf(VISIBLE + b'1 g\n' + SECOND))
    fact = snapshot.facts[0]
    with database.session() as db:
        snapshot = confirm_facts(matter.id, 1, [FactDecision(fact_id=fact.id, decision='rejected',
            confirmed_value=fact.typed_value, reason='SYNTHETIC visual uncertainty')], actor, db=db)
    context = review_context(p, database, actor, matter, version, snapshot)
    with database.session() as db:
        _, anchors, _, _, _ = current_manifest(context, actor, db, prompt_configuration(model_configuration(MockProvider())))
        assert not anchors
        run = run_review(context, MockProvider(), actor=actor, db=db)
        assert not run.findings
        assert all(not item.examined_anchor_ids for item in run.coverage)
        assert any('质量' in limitation for limitation in run.limitations)


def test_safe_page_fact_usable_while_other_page_is_manual(tmp_path):
    data = pdf([VISIBLE + SECOND, VISIBLE + b'1 g\n' + SECOND])
    p, database, actor, matter, _, parsed, snapshot = persisted(tmp_path, data)
    assert 'page:1:read' in parsed.parts and 'page:2:manual' in parsed.parts
    fact = snapshot.facts[0]
    with database.session() as db:
        confirmed = confirm_facts(matter.id, 1, [FactDecision(fact_id=fact.id, decision='confirmed',
            confirmed_value=fact.typed_value, reason='SYNTHETIC visible first page')], actor, db=db)
        result = calculate_expression(SafeExpression(ast={'kind': 'variable', 'name': 'amount'}, unit='CNY'),
            {'amount': Decimal('999999')}, inputs=(CalculationInput(name='amount', value='999999', unit='CNY', fact_ids=(fact.id,)),),
            matter_id=matter.id, actor=actor, db=db)
        assert confirmed.version == 2 and result.value == Decimal('999999')


REVIEW_RISKS = [
    ('extgs_linewidth', VISIBLE + SECOND + b'/GS1 gs 1 G 60 704 m 360 704 l S\n',
        {'gs': b'<< /LW 54 >>'}, 'PDF_DRAWING_EFFECT_REQUIRES_CONFIRMATION'),
    ('curve_controls', VISIBLE + SECOND + b'1 G 30 w 60 650 m 60 710 340 710 340 650 c S\n',
        {}, 'PDF_DRAWING_EFFECT_REQUIRES_CONFIRMATION'),
    ('stroke_text_background', b'0 g 60 670 300 25 re f\n' + VISIBLE + b'1 g 0 G 1 Tr\n' + SECOND,
        {}, 'PDF_TEXT_BACKGROUND_REQUIRES_CONFIRMATION'),
]


@pytest.mark.parametrize('name,content,kwargs,reason', REVIEW_RISKS, ids=[r[0] for r in REVIEW_RISKS])
def test_reviewed_occlusion_pdf_is_manual(name, content, kwargs, reason):
    parsed = parse_pdf(visual_pdf(content, **kwargs), uuid4(), load_settings())
    assert parsed.parts == ('page:1:manual',)
    assert f'{reason}:page:1' in parsed.quality_issues
    assert '999999' in parsed.anchors[0].quote


@pytest.mark.parametrize('name,content,kwargs,reason', REVIEW_RISKS, ids=[r[0] for r in REVIEW_RISKS])
def test_reviewed_occlusion_cannot_cross_actual_fact_consumers(tmp_path, name, content, kwargs, reason):
    specs = [('total_price', {'kind': 'decimal', 'value': '999999'}, 'CNY'),
        ('addendum_price', {'kind': 'decimal', 'value': '13750'}, 'CNY'),
        ('prior_month_actual_paid', {'kind': 'decimal', 'value': '999999'}, 'CNY'),
        ('prior_month_actual_paid_period', {'kind': 'text', 'value': 'SYNTHETIC prior-month period'}, None)]
    p, database, actor, matter, version, parsed, snapshot = persisted(tmp_path,
        visual_pdf(content, **kwargs), fact_specs=specs)
    outcomes = {}

    def outcome(name, operation):
        try:
            operation()
            outcomes[name] = 'ALLOWED'
        except ServiceError as exc:
            outcomes[name] = exc.code

    # Real confirmation transactions are rolled back only to keep each probe
    # independent. No parser/provider/source validator is replaced or mocked.
    with database.session() as db:
        for decision in ('confirmed', 'corrected'):
            boundary = db.begin_nested()
            value = snapshot.facts[0].typed_value if decision == 'confirmed' else {'kind': 'decimal', 'value': '13750'}
            outcome(decision, lambda: confirm_facts(matter.id, 1,
                [FactDecision(fact_id=snapshot.facts[0].id, decision=decision,
                    confirmed_value=value, reason='SYNTHETIC visual source probe')], actor, db=db))
            boundary.rollback()
        # The historical snapshot is written through the actual append-only
        # store to exercise consumers even when old confirmation bypassed B1b.
        historical = tuple(Fact(**{**fact.model_dump(mode='python'), 'version': 2,
            'confirmation_status': 'confirmed', 'confirmed_by': actor.user_id,
            'confirmed_at': datetime.now(timezone.utc)}) for fact in snapshot.facts)
        snapshot = FactSnapshot(version=2, facts=historical, sha256=p.fact_snapshot_sha256(historical))
        p.save_fact_snapshot(matter.id, snapshot, actor, db)
    context = review_context(p, database, actor, matter, version, snapshot)
    with database.session() as db:
        outcome('calculation', lambda: calculate_expression(
            SafeExpression(ast={'kind': 'variable', 'name': 'amount'}, unit='CNY'), {'amount': Decimal('999999')},
            inputs=(CalculationInput(name='amount', value='999999', unit='CNY', fact_ids=(snapshot.facts[0].id,)),),
            matter_id=matter.id, actor=actor, db=db))
        outcome('payment', lambda: payment_base_facts(matter.id, actor=actor, db=db))
        outcome('manifest', lambda: current_manifest(context, actor, db,
            prompt_configuration(model_configuration(MockProvider()))))
        outcome('review', lambda: run_review(context, MockProvider(), actor=actor, db=db))
    assert outcomes == {key: 'SOURCE_VISUAL_CONFIRMATION_REQUIRED'
        for key in ('confirmed', 'corrected', 'calculation', 'payment', 'manifest', 'review')}
    assert parsed.parts == ('page:1:manual',) and f'{reason}:page:1' in parsed.quality_issues


@pytest.mark.parametrize('state', [b'/LW 54', b'/LC 1', b'/LJ 1', b'/ML 20',
    b'/D [[4 1] 0]', b'/RI /AbsoluteColorimetric', b'/FL 0.5'])
def test_used_extgstate_paint_attributes_not_implemented_by_extractor_are_manual(state):
    parsed = parse_pdf(visual_pdf(VISIBLE + SECOND + b'/GS1 gs\n', gs=b'<< ' + state + b' >>'), uuid4(), load_settings())
    assert parsed.parts == ('page:1:manual',)
    assert 'PDF_DRAWING_EFFECT_REQUIRES_CONFIRMATION:page:1' in parsed.quality_issues


@pytest.mark.parametrize('path', [b'60 710 340 710 340 650 c', b'340 750 340 650 v', b'60 750 340 650 y'])
def test_non_linear_stroke_geometry_is_not_certified_by_endpoint_boxes(path):
    parsed = parse_pdf(visual_pdf(VISIBLE + SECOND + b'1 G 30 w 60 650 m ' + path + b' S\n'), uuid4(), load_settings())
    assert parsed.parts == ('page:1:manual',)
    assert 'PDF_DRAWING_EFFECT_REQUIRES_CONFIRMATION:page:1' in parsed.quality_issues


def test_mixed_text_mode_checks_stroke_and_fill_against_background():
    content = b'0 g 60 670 300 25 re f\n' + VISIBLE + b'0.7 g 0 G 2 Tr\n' + SECOND
    parsed = parse_pdf(visual_pdf(content), uuid4(), load_settings())
    assert parsed.parts == ('page:1:manual',)
    assert 'PDF_TEXT_BACKGROUND_REQUIRES_CONFIRMATION:page:1' in parsed.quality_issues


@pytest.mark.parametrize('content,kwargs', [
    (VISIBLE + b'0.1 0.2 0.4 rg\n' + SECOND, {}),
    (b'0.9 g 60 670 300 25 re f 0 g\n' + VISIBLE + SECOND, {}),
    (b'0.9 g 60 670 300 25 re f 0 g\n' + VISIBLE + b'1 g 0.1 0.2 0.4 RG 1 Tr\n' + SECOND, {}),
    (b'0.9 g 60 670 300 25 re f 0 g\n' + VISIBLE + b'0.1 0.2 0.4 rg 0 G 2 Tr\n' + SECOND, {}),
    (VISIBLE + SECOND, {'gs': b'<< /LW 54 /LC 1 /LJ 1 /D [[4 1] 0] >>'}),
    (VISIBLE + SECOND + b'/GS1 gs\n', {'gs': b'<< /Type /ExtGState /ca 1 /CA 1 /BM /Normal /SMask /None >>'}),
])
def test_supported_high_contrast_colors_and_unused_effects_remain_read(content, kwargs):
    parsed = parse_pdf(visual_pdf(content, **kwargs), uuid4(), load_settings())
    assert parsed.parts == ('page:1:read',)
    assert parsed.quality_issues == () and parsed.unsupported_parts == ()

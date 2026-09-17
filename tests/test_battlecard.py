"""Tests for the battlecard builder.

Run with: python3 -m pytest tests -q
"""

import os
import sys
import zipfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from battlecards import attributesmart, brand, compat, library, schema, service  # noqa: E402
from battlecards.builder import build_presentation  # noqa: E402


@pytest.fixture
def deck_path(tmp_path):
    payload = library.scaffold('RELEX Solutions', 'InventorySmart')
    payload['proof_points'] = [{
        'stat': '18%', 'label': 'Forecast accuracy gain',
        'detail': 'A grocery chain lifted item level accuracy in one season.',
        'source': 'https://www.impactanalytics.co',
    }]
    result = service.build(payload, str(tmp_path))
    return result['path']


# ── copy rules ──────────────────────────────────────────────────────────────

def test_sanitize_removes_banned_dashes():
    assert schema.sanitize_text('Fast planning — every week') == 'Fast planning, every week'
    assert schema.sanitize_text('Range 10–20 units') == 'Range 10, 20 units'


def test_lint_flags_terminal_preposition():
    issues = schema.lint_copy('That is the gap they cannot deliver on.', 'test')
    assert any(issue['rule'] == 'terminal_preposition' for issue in issues)


def test_lint_flags_faq_heading():
    issues = schema.lint_copy('See the FAQ for detail.', 'test')
    assert any(issue['rule'] == 'faq_heading' for issue in issues)


def test_lint_flags_stale_statistic():
    issues = schema.lint_copy('Margins rose 12% in 2021.', 'test')
    assert any(issue['rule'] == 'stat_recency' for issue in issues)


def test_script_urls_are_dropped():
    card = schema.normalize({
        'meta': {'competitor': 'Acme'},
        'their_strengths': ['Broad suite'],
        'resources': [{'label': 'Bad', 'url': 'javascript:alert(1)'},
                      {'label': 'Good', 'url': 'www.impactanalytics.co'}],
    })
    assert card['resources'][0]['url'] == ''
    assert card['resources'][1]['url'] == 'https://www.impactanalytics.co'


def test_validate_requires_a_competitor_and_content():
    result = schema.validate(schema.normalize({}))
    assert len(result['errors']) == 2


# ── brand rules ─────────────────────────────────────────────────────────────

def test_one_solution_colour_per_card():
    for product, solution in brand.PRODUCT_SOLUTIONS.items():
        theme = brand.Theme.for_solution(brand.solution_for_product(product))
        assert theme.accent == brand.SOLUTION_COLORS[solution]
        assert theme.page_bg == brand.OFF_WHITE
        assert theme.ink == brand.BLACK


def test_readable_text_colour_on_brand_fills():
    assert brand.readable_on(brand.IMPACT_BLUE) == brand.WHITE
    assert brand.readable_on(brand.OFF_WHITE) == brand.BLACK
    assert brand.readable_on(brand.SOLUTION_COLORS['inventory_replenishment']) == brand.BLACK


def test_white_logo_variant_is_generated():
    path = brand.ensure_white_logo()
    assert path and os.path.exists(path)


def test_only_palette_colours_reach_the_deck(deck_path):
    allowed = {str(color) for color in [
        brand.IMPACT_BLUE, brand.OFF_WHITE, brand.BLACK, brand.WHITE,
        brand.ACCENT_ORANGE, brand.GRAY_1, brand.GRAY_2, brand.GRAY_3,
    ]}
    allowed |= {str(color) for color in brand.SOLUTION_COLORS.values()}
    # Two families of derived tint, and nothing else: White over Impact Blue for
    # text on blue fills, and the solution accent toward White for the stat panel.
    allowed |= {str(brand.mix(brand.WHITE, brand.IMPACT_BLUE, weight))
                for weight in (0.12, 0.35, 0.4, 0.45)}
    allowed |= {str(brand.mix(accent, brand.WHITE, 0.45))
                for accent in brand.SOLUTION_COLORS.values()}

    import re
    used = set()
    with zipfile.ZipFile(deck_path) as archive:
        for name in archive.namelist():
            if name.startswith('ppt/slides/slide'):
                xml = archive.read(name).decode('utf-8')
                used |= set(re.findall(r'<a:srgbClr val="([0-9A-Fa-f]{6})"', xml))
    assert used - allowed == set(), 'off palette colours: %s' % sorted(used - allowed)


# ── deck structure ──────────────────────────────────────────────────────────

def test_deck_builds_every_selected_section(deck_path):
    from pptx import Presentation
    presentation = Presentation(deck_path)
    assert len(presentation.slides._sldIdLst) >= 15


def test_slide_size_matches_the_house_template():
    """10 x 5.625in, the canvas the IA template uses, exactly."""
    card = schema.normalize(library.scaffold('Acme'))
    presentation = build_presentation(card)
    assert presentation.slide_width == 9144000
    assert presentation.slide_height == 5143500


def test_long_content_paginates():
    payload = library.scaffold('Acme', 'PriceSmart')
    payload['objections'] = [{'objection': 'Objection %d' % i, 'response': 'Answer', 'proof': 'Proof'}
                             for i in range(7)]
    card = schema.normalize(payload)
    presentation = build_presentation(card)
    titles = []
    for slide in presentation.slides:
        for shape in slide.shapes:
            if shape.has_text_frame and shape.text_frame.text.strip() == 'Objection handling':
                titles.append(shape.text_frame.text)
    assert len(titles) == 4  # seven objections, two per slide on the house canvas


def test_sections_can_be_narrowed():
    payload = library.scaffold('Acme')
    payload['sections'] = ['one_pager']
    card = schema.normalize(payload)
    presentation = build_presentation(card)
    assert len(presentation.slides._sldIdLst) == 2  # cover is always included


def test_speaker_notes_can_be_switched_off():
    payload = library.scaffold('Acme')
    payload['options'] = {'include_notes': False}
    presentation = build_presentation(schema.normalize(payload))
    for slide in presentation.slides:
        if slide.has_notes_slide:
            assert slide.notes_slide.notes_text_frame.text.strip() == ''


# ── Google Slides compatibility ─────────────────────────────────────────────

def test_deck_passes_the_google_slides_audit(deck_path):
    report = compat.audit(deck_path)
    assert report['ok'], report['findings']
    assert report['findings'] == []


def test_every_run_names_a_typeface(deck_path):
    with zipfile.ZipFile(deck_path) as archive:
        for name in archive.namelist():
            if not name.startswith('ppt/slides/slide'):
                continue
            xml = archive.read(name).decode('utf-8')
            if '<a:t>' in xml:
                assert '<a:latin typeface="Inter Tight"' in xml, name


def test_no_autofit_font_scaling(deck_path):
    with zipfile.ZipFile(deck_path) as archive:
        for name in archive.namelist():
            if name.startswith('ppt/slides/slide'):
                assert 'fontScale' not in archive.read(name).decode('utf-8')


def test_tables_carry_no_theme_style(deck_path):
    with zipfile.ZipFile(deck_path) as archive:
        for name in archive.namelist():
            if name.startswith('ppt/slides/slide'):
                assert 'tableStyleId' not in archive.read(name).decode('utf-8')


def test_audit_reports_a_broken_deck(tmp_path):
    path = str(tmp_path / 'bad.pptx')
    from pptx import Presentation
    from pptx.util import Inches
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1))
    box.text_frame.text = 'No typeface here'
    presentation.save(path)
    report = compat.audit(path)
    assert any(item['rule'] == 'run_font' for item in report['findings'])


# ── service layer ───────────────────────────────────────────────────────────

def test_filename_is_safe(tmp_path):
    payload = library.scaffold('../../evil name', 'PriceSmart')
    result = service.build(payload, str(tmp_path))
    assert '/' not in result['filename'] and '..' not in result['filename']
    assert result['filename'].endswith('.pptx')


def test_build_rejects_an_empty_card(tmp_path):
    with pytest.raises(ValueError):
        service.build({}, str(tmp_path))


def test_presets_cover_every_solution():
    presets = service.presets()
    assert {entry['key'] for entry in presets['solutions']} == set(brand.SOLUTION_COLORS)
    assert len(presets['sections']) == len(schema.SECTION_ORDER)

# ── house template conformance ──────────────────────────────────────────────

def test_data_intelligence_accent_matches_the_shipping_theme():
    """The IA theme carries BFD1F5, which wins over the written spec."""
    assert str(brand.SOLUTION_COLORS['data_intelligence']) == 'BFD1F5'


def test_titles_are_two_tone(deck_path):
    """Every content slide splits its title into Black then Impact Blue."""
    import re
    with zipfile.ZipFile(deck_path) as archive:
        two_tone = 0
        for name in sorted(archive.namelist()):
            if not name.startswith('ppt/slides/slide'):
                continue
            xml = archive.read(name).decode('utf-8')
            has_black = 'srgbClr val="1C1B1B"' in xml
            has_blue = 'srgbClr val="264CD7"' in xml
            if has_black and has_blue:
                two_tone += 1
    assert two_tone >= 10, 'expected most slides to carry a two tone title'


def test_no_accent_rule_under_titles():
    """The house template separates title from body with whitespace only.

    A rule would show up as a wide, very short filled rectangle sitting just
    below the title band.
    """
    from pptx.util import Inches
    card = schema.normalize(library.scaffold('Acme', 'PriceSmart'))
    presentation = build_presentation(card)
    for slide in presentation.slides:
        for shape in slide.shapes:
            if shape.height is None or shape.width is None or shape.top is None:
                continue
            thin = shape.height <= Inches(0.06)
            wide = shape.width >= Inches(1.0)
            in_header = Inches(0.8) <= shape.top <= Inches(1.0)
            assert not (thin and wide and in_header), 'accent rule found under a title'


def test_footer_uses_the_secondary_font(deck_path):
    with zipfile.ZipFile(deck_path) as archive:
        xml = archive.read('ppt/slides/slide2.xml').decode('utf-8')
    assert '<a:latin typeface="Lato"' in xml


def test_cards_carry_a_soft_shadow(deck_path):
    with zipfile.ZipFile(deck_path) as archive:
        xml = archive.read('ppt/slides/slide2.xml').decode('utf-8')
    assert '<a:outerShdw' in xml
    # Reflection, glow and soft edge do not survive a Google Slides import.
    for unsupported in ('<a:reflection', '<a:glow', '<a:softEdge'):
        assert unsupported not in xml


# ── citations ───────────────────────────────────────────────────────────────

def test_citation_kinds():
    assert schema.citation_kind('https://example.com/x') == 'link'
    assert schema.citation_kind('IA AttributeSmart NRF 2026 deck') == 'internal'
    assert schema.citation_kind('') == 'missing'
    assert schema.citation_kind('internal') == 'unclear'


def test_internal_citation_satisfies_an_internal_card():
    card = schema.normalize({
        'meta': {'competitor': 'Acme', 'distribution': 'internal'},
        'their_strengths': ['Broad suite'],
        'proof_points': [{'stat': '60%', 'label': 'Saving',
                          'source': 'IA AttributeSmart NRF 2026 deck'}],
    })
    rules = {warning['rule'] for warning in schema.validate(card)['warnings']}
    assert 'source_link' not in rules and 'external_source' not in rules


def test_customer_facing_card_still_demands_a_link():
    card = schema.normalize({
        'meta': {'competitor': 'Acme', 'distribution': 'customer'},
        'their_strengths': ['Broad suite'],
        'proof_points': [{'stat': '60%', 'label': 'Saving',
                          'source': 'IA AttributeSmart NRF 2026 deck'}],
    })
    rules = {warning['rule'] for warning in schema.validate(card)['warnings']}
    assert 'external_source' in rules


# ── AttributeSmart cards ────────────────────────────────────────────────────

def test_every_attributesmart_card_is_clean():
    for name in attributesmart.COMPETITORS:
        card = schema.normalize(attributesmart.card_for(name))
        checks = schema.validate(card)
        assert checks['errors'] == [], (name, checks['errors'])
        assert checks['warnings'] == [], (name, checks['warnings'])


def test_unsourced_competitor_capabilities_stay_unknown():
    """The cards must never assert a gap the public record does not support."""
    card = attributesmart.card_for('o9 Solutions')
    sourced = set(attributesmart.COMPETITORS['o9 Solutions']['ratings'])
    for row in card['comparison']:
        if row['capability'] not in sourced:
            assert row['competitor'] == 'unknown', row['capability']
            assert 'do not assert' in row['note']


def test_attributesmart_cards_cite_their_sources():
    for name in attributesmart.COMPETITORS:
        card = attributesmart.card_for(name)
        urls = [row['url'] for row in card['resources'] if row.get('url')]
        assert len(urls) >= 2, name
        for row in card['proof_points']:
            assert schema.citation_kind(row['source']) in ('link', 'internal')


def test_unknown_competitor_is_rejected():
    with pytest.raises(KeyError):
        attributesmart.card_for('Not A Real Vendor')


def test_attributesmart_cards_build(tmp_path):
    for name in attributesmart.COMPETITORS:
        result = service.build(attributesmart.card_for(name), str(tmp_path))
        assert result['compatibility']['ok'], (name, result['compatibility']['findings'])
        assert result['slide_count'] >= 15


# ── auth gate ───────────────────────────────────────────────────────────────

def test_auth_is_off_without_credentials(monkeypatch):
    from battlecards import auth
    monkeypatch.delenv('IA_AUTH_USER', raising=False)
    monkeypatch.delenv('IA_AUTH_PASSWORD', raising=False)
    assert auth.credentials() is None
    assert auth.is_enabled() is False


def test_auth_gate_rejects_and_accepts(monkeypatch):
    import base64
    from flask import Flask
    from battlecards import auth

    monkeypatch.setenv('IA_AUTH_USER', 'ia')
    monkeypatch.setenv('IA_AUTH_PASSWORD', 'secret')
    app = Flask(__name__)
    auth.install(app)

    @app.route('/private')
    def private():
        return 'ok'

    @app.route('/healthz')
    def healthz():
        return 'alive'

    client = app.test_client()
    assert client.get('/private').status_code == 401
    assert client.get('/healthz').status_code == 200  # probe stays open

    def header(user, password):
        token = base64.b64encode(('%s:%s' % (user, password)).encode()).decode()
        return {'Authorization': 'Basic ' + token}

    assert client.get('/private', headers=header('ia', 'wrong')).status_code == 401
    assert client.get('/private', headers=header('nope', 'secret')).status_code == 401
    assert client.get('/private', headers=header('ia', 'secret')).status_code == 200

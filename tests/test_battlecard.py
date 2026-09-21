"""Tests for the battlecard builder.

Run with: python3 -m pytest tests -q
"""

import json
import os
import re
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


# ── depth presets ───────────────────────────────────────────────────────────

def test_each_depth_hits_its_advertised_slide_count(tmp_path):
    """The label promises a range. The build must land inside it."""
    expected = {'summary': (6, 8), 'standard': (11, 13), 'technical': (17, 20)}
    for depth, (low, high) in expected.items():
        payload = attributesmart.card_for('o9 Solutions')
        payload['meta']['depth'] = depth
        result = service.build(payload, str(tmp_path))
        assert low <= result['slide_count'] <= high, (depth, result['slide_count'])


def test_depth_caps_trim_rows():
    payload = attributesmart.card_for('Oracle Retail')
    card = schema.apply_depth(schema.normalize(payload), 'summary')
    caps = schema.DEPTHS['summary']['caps']
    for key, cap in caps.items():
        assert len(card.get(key, [])) <= cap, key


def test_a_card_without_a_depth_keeps_every_section(tmp_path):
    """A curated card lists its own sections and must not be silently trimmed."""
    payload = attributesmart.card_for('o9 Solutions')
    assert 'depth' not in payload['meta']
    result = service.build(payload, str(tmp_path))
    assert result['slide_count'] >= 17


def test_depth_is_recorded_on_the_card():
    card = schema.normalize({'meta': {'competitor': 'Acme', 'depth': 'summary'},
                             'their_strengths': ['x']})
    assert card['meta']['depth'] == 'summary'
    assert schema.normalize({'meta': {'competitor': 'Acme'}})['meta']['depth'] == ''


# ── AI layer ────────────────────────────────────────────────────────────────

def test_ai_reports_unavailable_without_a_credential(monkeypatch):
    from battlecards import ai
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    monkeypatch.delenv('ANTHROPIC_AUTH_TOKEN', raising=False)
    monkeypatch.setattr(ai.os.path, 'isdir', lambda path: False)
    assert ai.available() is False


def test_ai_available_with_a_key(monkeypatch):
    from battlecards import ai
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'sk-ant-not-a-real-key')
    assert ai.available() is True


def test_generate_events_explains_a_missing_credential(monkeypatch):
    from battlecards import ai
    monkeypatch.setattr(ai, 'available', lambda: False)
    events = list(ai.generate_events('Acme', 'AttributeSmart'))
    assert len(events) == 1
    assert events[0]['type'] == 'error'
    assert 'ANTHROPIC_API_KEY' in events[0]['message']


def test_generate_events_rejects_an_empty_competitor():
    from battlecards import ai
    events = list(ai.generate_events('', 'AttributeSmart'))
    assert events[0]['type'] == 'error'


def test_model_is_opus_5():
    from battlecards import ai
    assert ai.MODEL == 'claude-opus-5'


def test_ground_truth_carries_the_verified_attributesmart_facts():
    from battlecards import ai
    facts = ai._product_facts('AttributeSmart')
    assert '10,000' in facts and 'CNN' in facts and 'OCR' in facts
    assert attributesmart.IA_CITATION in facts
    # Another product must not inherit AttributeSmart's numbers.
    assert 'CNN' not in ai._product_facts('PriceSmart')


def test_system_prompt_states_the_honesty_rules_and_caches_them():
    from battlecards import ai
    blocks = ai._system_prompt('AttributeSmart', 'o9 Solutions')
    stable = blocks[0]
    assert stable['cache_control'] == {'type': 'ephemeral'}
    assert 'Never state a capability' in stable['text']
    assert 'no en dashes' in stable['text']
    # The volatile competitor name sits after the cached prefix.
    assert 'o9 Solutions' in blocks[1]['text']
    assert 'o9 Solutions' not in stable['text']


def test_generated_card_schema_restricts_ratings():
    from battlecards import ai
    ratings = ai.CARD_SCHEMA['properties']['comparison']['items']['properties']
    assert ratings['competitor']['enum'] == list(schema.RATING_VALUES)
    assert 'unknown' in ratings['competitor']['enum']


def test_curated_research_wins_over_generated_content():
    from battlecards import ai
    thin = {'their_strengths': ['generated guess'], 'comparison': [],
            'meta': {'headline': 'generated'}}
    merged = ai._merge_curated(thin, 'o9 Solutions', 'AttributeSmart')
    curated = attributesmart.COMPETITORS['o9 Solutions']
    assert merged['their_strengths'] == curated['strengths']
    assert merged['_curated'] is True
    # A competitor with no curated card keeps the generated content.
    untouched = ai._merge_curated(dict(thin), 'Some New Vendor', 'AttributeSmart')
    assert untouched['their_strengths'] == ['generated guess']


# ── routes ──────────────────────────────────────────────────────────────────

@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv('IA_AUTH_USER', raising=False)
    monkeypatch.delenv('IA_AUTH_PASSWORD', raising=False)
    import app as flask_app
    flask_app.app.config['TESTING'] = True
    return flask_app.app.test_client()


def test_battlecard_builder_owns_the_landing_page(client):
    body = client.get('/').data.decode()
    assert 'Battlecard Builder' in body
    assert 'Which Impact Analytics product?' in body
    # The standardizer is no longer the front door.
    assert 'Upload & Convert' not in body


def test_standardizer_still_reachable(client):
    assert client.get('/standardizer').status_code == 200
    assert 'Standardize Now' in client.get('/standardizer').data.decode()


def test_old_battlecard_link_still_works(client):
    assert client.get('/battlecard').status_code == 200


def test_status_route_lists_the_depths(client):
    data = client.get('/api/battlecard/status').get_json()
    assert data['model'] == 'claude-opus-5'
    assert {entry['key'] for entry in data['depths']} == set(schema.DEPTHS)
    for entry in data['depths']:
        assert entry['label'] and entry['slides'] and entry['blurb']


def test_chat_route_refuses_without_a_credential(client, monkeypatch):
    import app as flask_app
    monkeypatch.setattr(flask_app.battlecard_ai, 'available', lambda: False)
    response = client.post('/api/battlecard/chat', json={'messages': [
        {'role': 'user', 'content': 'hi'}]})
    assert response.status_code == 503
    assert 'ANTHROPIC_API_KEY' in response.get_json()['error']


def test_generate_route_streams_events(client, monkeypatch):
    import app as flask_app

    def fake(competitor, product, depth, notes, economy=False):
        yield {'type': 'status', 'step': 'research', 'message': 'searching'}
        yield {'type': 'card', 'card': {'meta': {'competitor': competitor}},
               'curated': False, 'research': 'brief', 'cost': {}}

    monkeypatch.setattr(flask_app.battlecard_ai, 'generate_events', fake)
    response = client.post('/api/battlecard/generate',
                           json={'competitor': 'Acme', 'ia_product': 'AttributeSmart'})
    assert response.status_code == 200
    assert response.mimetype == 'text/event-stream'
    body = response.get_data(as_text=True)
    assert '"type": "status"' in body and '"type": "card"' in body


# ── shared library ──────────────────────────────────────────────────────────

def test_render_postgres_scheme_is_rewritten(monkeypatch):
    """Render hands out postgres:// URLs; psycopg needs postgresql://."""
    from battlecards import store
    monkeypatch.setenv('DATABASE_URL', 'postgres://user:pw@host/db')
    assert store.database_url() == 'postgresql://user:pw@host/db'
    monkeypatch.setenv('DATABASE_URL', 'postgresql://user:pw@host/db')
    assert store.database_url() == 'postgresql://user:pw@host/db'


def test_library_is_disabled_without_a_database(monkeypatch):
    from battlecards import store
    monkeypatch.delenv('DATABASE_URL', raising=False)
    assert store.enabled() is False
    assert store.init() is False
    assert store.save({'meta': {'competitor': 'Acme'}}) == {}
    assert store.listing() == []
    assert store.get(1) == {}
    assert store.delete(1) is False
    assert store.stats() == {'enabled': False, 'cards': 0,
                             'competitors': 0, 'products': 0}


def test_library_page_explains_a_missing_database(client, monkeypatch):
    import app as flask_app
    monkeypatch.setattr(flask_app.battlecard_store, 'enabled', lambda: False)
    body = flask_app.app.test_client().get('/library').data.decode()
    assert 'library is not connected' in body
    assert 'DATABASE_URL' in body


def test_build_still_works_without_a_library(client, monkeypatch, tmp_path):
    """A missing database must never break the deck build."""
    import app as flask_app
    monkeypatch.setattr(flask_app.battlecard_store, 'save', lambda *a, **k: {})
    payload = attributesmart.card_for('o9 Solutions')
    payload['meta']['depth'] = 'summary'
    response = client.post('/api/battlecard/build', json=payload)
    assert response.status_code == 200
    body = response.get_json()
    assert body['library_entry'] is None
    assert body['slide_count'] >= 6


# These need a real Postgres. DATABASE_URL points at one in CI and locally.
pg = pytest.mark.skipif(not os.environ.get('DATABASE_URL'),
                        reason='set DATABASE_URL to run the library tests')


@pg
def test_store_round_trip():
    from battlecards import store
    assert store.init(force=True) is True
    payload = attributesmart.card_for('Oracle Retail')
    payload['meta']['depth'] = 'standard'
    saved = store.save(payload, slide_count=13, research='a brief',
                       author='tester@impactanalytics.co', curated=True)
    assert saved['id'] and saved['competitor'] == 'Oracle Retail'
    assert saved['slide_count'] == 13 and saved['curated'] is True
    # unverified counts the unknown competitor ratings
    expected = sum(1 for row in payload['comparison']
                   if row['competitor'] == 'unknown')
    assert saved['unverified'] == expected

    full = store.get(saved['id'])
    assert full['card']['meta']['competitor'] == 'Oracle Retail'
    assert len(full['card']['comparison']) == len(payload['comparison'])
    assert full['research'] == 'a brief'
    assert full['views'] >= 1
    assert store.delete(saved['id']) is True
    assert store.get(saved['id']) == {}


@pg
def test_store_filters():
    from battlecards import store
    store.init(force=True)
    made = []
    for name, product in (('Zeta Planning', 'AttributeSmart'),
                          ('Omega Pricing', 'PriceSmart')):
        payload = attributesmart.card_for('o9 Solutions')
        payload['meta']['competitor'] = name
        payload['meta']['ia_product'] = product
        made.append(store.save(payload, slide_count=9)['id'])
    try:
        assert [row['competitor'] for row in store.listing(query='zeta')] == ['Zeta Planning']
        products = {row['ia_product'] for row in store.listing(product='PriceSmart')}
        assert products == {'PriceSmart'}
        assert store.listing(limit=1) and len(store.listing(limit=1)) == 1
    finally:
        for card_id in made:
            store.delete(card_id)


@pg
def test_library_routes(client):
    from battlecards import store
    store.init(force=True)
    payload = attributesmart.card_for('RELEX Solutions')
    payload['meta']['depth'] = 'summary'
    saved = store.save(payload, slide_count=7)
    try:
        listing = client.get('/api/library').get_json()
        assert listing['stats']['enabled'] is True
        assert any(row['id'] == saved['id'] for row in listing['cards'])
        assert 'AttributeSmart' in listing['products']

        detail = client.get('/api/library/%d' % saved['id']).get_json()
        assert detail['card']['meta']['competitor'] == 'RELEX Solutions'

        rebuilt = client.post('/api/library/%d/build' % saved['id'],
                              json={'depth': 'technical'}).get_json()
        assert rebuilt['slide_count'] >= 17  # rebuilt longer than it was saved

        assert client.get('/api/library/99999999').status_code == 404
        assert client.post('/api/library/99999999/build').status_code == 404
    finally:
        store.delete(saved['id'])


@pg
def test_generated_cards_land_in_the_library(client):
    """The build route is what shares a card, so it must write the row."""
    from battlecards import store
    store.init(force=True)
    before = store.stats()['cards']
    payload = attributesmart.card_for('Blue Yonder')
    payload['meta']['depth'] = 'summary'
    body = client.post('/api/battlecard/build',
                       json=dict(payload, research='brief', curated=True)).get_json()
    entry = body['library_entry']
    assert entry and entry['competitor'] == 'Blue Yonder'
    assert store.stats()['cards'] == before + 1
    assert store.get(entry['id'])['research'] == 'brief'
    store.delete(entry['id'])


# ── cost accounting ─────────────────────────────────────────────────────────

class _Usage:
    """Stands in for an SDK usage object."""

    def __init__(self, input_tokens=0, cache_creation_input_tokens=0,
                 cache_read_input_tokens=0, output_tokens=0):
        self.input_tokens = input_tokens
        self.cache_creation_input_tokens = cache_creation_input_tokens
        self.cache_read_input_tokens = cache_read_input_tokens
        self.output_tokens = output_tokens


def test_cost_uses_the_published_opus_5_rates():
    from battlecards import ai
    assert ai.PRICING['input'] == 5.00 and ai.PRICING['output'] == 25.00
    # One million of each, so the arithmetic is readable.
    one = ai.usage_cost(_Usage(input_tokens=1_000_000))
    assert one['usd'] == 5.0
    assert ai.usage_cost(_Usage(output_tokens=1_000_000))['usd'] == 25.0
    # Cache writes bill above input, reads well below it.
    assert ai.usage_cost(_Usage(cache_creation_input_tokens=1_000_000))['usd'] == 6.25
    assert ai.usage_cost(_Usage(cache_read_input_tokens=1_000_000))['usd'] == 0.50


def test_cost_accumulates_across_calls():
    from battlecards import ai
    total = {}
    ai.add_cost(total, _Usage(input_tokens=40_000, output_tokens=8_000))
    ai.add_cost(total, _Usage(input_tokens=5_000, cache_read_input_tokens=1_000,
                              output_tokens=6_000))
    assert total['calls'] == 2
    assert total['input'] == 45_000 and total['output'] == 14_000
    expected = (45_000 * 5 + 1_000 * 0.5 + 14_000 * 25) / 1_000_000
    assert total['usd'] == round(expected, 4)


def test_usage_survives_a_usage_object_missing_cache_fields():
    """Older or partial usage payloads must not raise."""
    from battlecards import ai

    class Bare:
        input_tokens = 100
        output_tokens = 50

    assert ai.usage_cost(Bare())['usd'] > 0


def test_economy_mode_is_cheaper_on_every_axis():
    from battlecards import ai
    assert ai.ECONOMY['searches'] < ai.STANDARD['searches']
    assert ai.ECONOMY['max_tokens'] < ai.STANDARD['max_tokens']
    assert ai.ECONOMY['effort'] == 'low' and ai.STANDARD['effort'] == 'high'
    assert ai._search_tool(3)['max_uses'] == 3


def test_generate_route_passes_the_economy_flag(client, monkeypatch):
    import app as flask_app
    seen = {}

    def fake(competitor, product, depth, notes, economy=False):
        seen['economy'] = economy
        yield {'type': 'card', 'card': {'meta': {'competitor': competitor}},
               'curated': False, 'research': '', 'cost': {}}

    monkeypatch.setattr(flask_app.battlecard_ai, 'generate_events', fake)
    client.post('/api/battlecard/generate',
                json={'competitor': 'Acme', 'economy': True})
    assert seen['economy'] is True
    client.post('/api/battlecard/generate', json={'competitor': 'Acme'})
    assert seen['economy'] is False


def test_status_route_publishes_the_rates(client):
    pricing = client.get('/api/battlecard/status').get_json()['pricing']
    assert pricing['input'] == 5.00 and pricing['output'] == 25.00


def test_building_a_saved_card_costs_nothing(tmp_path, monkeypatch):
    """The curated cards must never touch the API. That is the zero cost path."""
    from battlecards import ai

    def explode(*args, **kwargs):
        raise AssertionError('the API must not be called to build a saved card')

    monkeypatch.setattr(ai, '_client', explode)
    result = service.build(attributesmart.card_for('o9 Solutions'), str(tmp_path))
    assert result['slide_count'] >= 15


# ── the card JSON path ──────────────────────────────────────────────────────
# A real run failed with "The compiled grammar is too large, which would cause
# performance issues." CARD_SCHEMA has twelve nested object shapes, which is past
# what output_config.format can compile. The shape is now a prompt contract and
# the JSON is parsed here, so the request carries no grammar at all.

def test_no_grammar_is_ever_compiled():
    """The regression guard. A json_schema format would 400 on this schema."""
    import inspect
    from battlecards import ai
    source = inspect.getsource(ai)
    assert 'json_schema' not in source
    assert "'format'" not in source


def test_the_shape_contract_comes_from_the_one_schema():
    from battlecards import ai
    contract = ai._shape_contract()
    assert 'their_strengths' in contract and 'comparison' in contract
    # Same definition the test below checks, so prompt and schema cannot drift.
    assert json.loads(contract) == ai.CARD_SCHEMA


@pytest.mark.parametrize('wrapped', [
    '{"a": 1}',
    '```json\n{"a": 1}\n```',
    '```\n{"a": 1}\n```',
    'Here is the card:\n\n{"a": 1}',
    '{"a": 1}\n\nI marked three rows Unclear.',
    'Sure.\n```json\n{"a": 1}\n```\nHope that helps.',
    '\n\n   {"a": 1}   \n',
])
def test_card_json_survives_model_drift(wrapped):
    from battlecards import ai
    assert ai._parse_card_json(wrapped) == {'a': 1}


def test_card_json_handles_nested_braces_and_escapes():
    from battlecards import ai
    out = ai._parse_card_json('{"a": {"b": "}"}, "c": "60% \\u2192 96%"}')
    assert out['a']['b'] == '}'
    assert '→' in out['c']


@pytest.mark.parametrize('bad', ['', '   ', 'I could not research that.',
                                 '[{"a": 1}]', '"just a string"'])
def test_unusable_output_raises_value_error(bad):
    """ValueError is what triggers the single retry, so the type matters."""
    from battlecards import ai
    with pytest.raises(ValueError):
        ai._parse_card_json(bad)


def test_truncation_is_named_as_truncation():
    from battlecards import ai
    with pytest.raises(ValueError) as caught:
        ai._parse_card_json('{"headline": "x", "rows": ["a"')
    assert 'max_tokens' in str(caught.value)


def test_token_ceilings_are_generous_enough_for_a_full_card():
    """max_tokens is a cap, not a spend. Economy saves on effort, not headroom."""
    from battlecards import ai
    card = json.dumps(attributesmart.card_for('Oracle Retail'))
    needed = len(card) // 3          # deliberately pessimistic chars-per-token
    assert ai.ECONOMY['max_tokens'] > needed, (ai.ECONOMY['max_tokens'], needed)
    assert ai.STANDARD['max_tokens'] > needed
    # Economy still costs less, through effort and searches.
    assert ai.ECONOMY['effort'] == 'low'
    assert ai.ECONOMY['searches'] < ai.STANDARD['searches']


# ── the chat transcript ─────────────────────────────────────────────────────
# A real run failed with "This model does not support assistant message prefill.
# The conversation must end with a user message." The panel greets the seller
# before they type and shows a placeholder bubble while a reply streams, so the
# transcript it posted began and ended with an assistant turn.

@pytest.mark.parametrize('history', [
    [{'role': 'assistant', 'content': 'Pick a competitor.'},
     {'role': 'user', 'content': 'which rows are unverified?'}],
    [{'role': 'user', 'content': 'hi'},
     {'role': 'assistant', 'content': 'Thinking'}],
    [{'role': 'assistant', 'content': 'welcome'},
     {'role': 'user', 'content': 'hi'},
     {'role': 'assistant', 'content': 'hello'},
     {'role': 'user', 'content': 'sharpen the win theme'},
     {'role': 'assistant', 'content': 'Thinking'}],
    [{'role': 'user', 'content': 'a'}, {'role': 'user', 'content': 'b'}],
])
def test_the_transcript_always_opens_and_closes_on_the_seller(history):
    from battlecards import ai
    messages = ai._chat_messages(history)
    assert messages, history
    assert messages[0]['role'] == 'user'
    assert messages[-1]['role'] == 'user'
    roles = [turn['role'] for turn in messages]
    assert all(a != b for a, b in zip(roles, roles[1:])), roles


@pytest.mark.parametrize('history', [
    [],
    [{'role': 'assistant', 'content': 'welcome'}],
    [{'role': 'assistant', 'content': 'welcome'}, {'role': 'assistant', 'content': 'and'}],
    [{'role': 'user', 'content': '   '}],
    [{'role': 'user', 'content': None}],
])
def test_a_transcript_with_nothing_to_answer_is_dropped(history):
    """No request at all beats a request the API will reject."""
    from battlecards import ai
    assert ai._chat_messages(history) == []


def test_a_repeated_role_is_folded_rather_than_sent_twice():
    from battlecards import ai
    messages = ai._chat_messages([{'role': 'user', 'content': 'first'},
                                  {'role': 'user', 'content': 'second'}])
    assert messages == [{'role': 'user', 'content': 'first\n\nsecond'}]


def test_chat_sends_a_valid_transcript_to_the_api(monkeypatch):
    """End to end through chat_stream, with the client faked out."""
    from battlecards import ai

    seen = {}

    class FakeStream:
        text_stream = iter(['Rows 3 and 7 ', 'are unverified.'])

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    class FakeMessages:
        def stream(self, **kwargs):
            seen.update(kwargs)
            return FakeStream()

    class FakeClient:
        messages = FakeMessages()

    monkeypatch.setattr(ai, '_client', lambda: FakeClient())
    answer = ''.join(ai.chat_stream(
        [{'role': 'assistant', 'content': 'Pick a competitor and a product.'},
         {'role': 'user', 'content': 'which rows are unverified?'},
         {'role': 'assistant', 'content': 'Thinking'}],
        card=attributesmart.card_for('o9 Solutions'), product='AttributeSmart'))
    assert answer == 'Rows 3 and 7 are unverified.'
    assert seen['messages'] == [{'role': 'user',
                                 'content': 'which rows are unverified?'}]
    assert seen['model'] == 'claude-opus-5'
    # The card reaches the model as system context, not as a fake dialogue turn.
    assert any('o9 Solutions' in block['text'] for block in seen['system'])


def test_chat_with_only_a_greeting_never_calls_the_api():
    from battlecards import ai

    def explode():
        raise AssertionError('there is no question to answer yet')

    original = ai._client
    ai._client = explode
    try:
        assert list(ai.chat_stream([{'role': 'assistant', 'content': 'welcome'}])) == []
    finally:
        ai._client = original


def test_the_panel_does_not_post_its_own_bubbles():
    """The client half of the fix, guarded so a UI edit cannot undo it."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    page = open(os.path.join(root, 'templates', 'battlecard.html')).read()
    # The transcript is snapshotted before the placeholder bubble is drawn.
    assert 'const history = chat.filter(m => m.content);' in page
    assert "say('assistant', 'Thinking', false)" in page
    # And the greeting is an interface note, so it is never sent as a turn.
    assert page.count('if (track) chat.push(') == 1


# ── company facts on the snapshot ───────────────────────────────────────────
# A real o9 card came back with "Not found" in every company fact box. Three
# causes: the curated snapshot shipped empty, _merge_curated never merged
# 'snapshot' at all, and economy mode gave three searches to a six part brief,
# so the capability questions spent the budget before the facts were asked for.

@pytest.mark.parametrize('competitor', sorted(attributesmart.COMPETITORS))
def test_every_curated_card_carries_sourced_company_facts(competitor):
    snapshot = attributesmart.card_for(competitor)['snapshot']
    filled = [field for field in ('headquarters', 'ownership', 'funding',
                                  'target_segment')
              if snapshot.get(field)]
    assert len(filled) >= 3, (competitor, snapshot)
    # Any fact that quotes a figure has to say where the figure came from, or
    # say plainly that it should not be quoted. A city name needs no citation;
    # a valuation does. That distinction is the whole discipline of the card.
    # Money and headcount are the figures a buyer will challenge, so those two
    # carry provenance or tell the seller not to quote them. A founding year or a
    # city needs no citation, and demanding one would only pad the slide.
    for field in ('funding', 'employees'):
        text = snapshot.get(field) or ''
        assert text, (competitor, field)
        assert any(word in text.lower() for word in (
            'per ', 'newsroom', 'investor', 'pitchbook', 'tracker', 'own ',
            'do not quote', 'do not present', 'no round', 'not published',
            'no venture')), (competitor, field, text)


def test_a_blank_curated_fact_is_left_for_the_researcher():
    """Blank means unsourced, so the slide stays quiet instead of asserting."""
    snapshot = attributesmart.card_for('o9 Solutions')['snapshot']
    assert snapshot['go_to_market'] == ''
    assert attributesmart.FACTS_NOTE


def test_curated_facts_reach_a_generated_card():
    """The merge bug: 'snapshot' was missing from the key list entirely."""
    from battlecards import ai
    generated = {'snapshot': {'headquarters': 'Not found. Verify before the call.',
                              'founded': 'Not found. Verify before the call.',
                              'go_to_market': 'Direct, per their careers page.'},
                 'meta': {}}
    merged = ai._merge_curated(generated, 'o9 Solutions', 'AttributeSmart')
    assert merged['snapshot']['headquarters'] == 'Dallas, Texas.'
    assert 'Sidhu' in merged['snapshot']['founded']
    # A field the curated card leaves blank keeps what the research found.
    assert merged['snapshot']['go_to_market'] == 'Direct, per their careers page.'


def test_a_generated_snapshot_survives_a_competitor_with_no_curated_card():
    from battlecards import ai
    card = {'snapshot': {'headquarters': 'Boston.'}, 'meta': {}}
    assert ai._merge_curated(card, 'Lily AI', 'AttributeSmart')['snapshot'] == {
        'headquarters': 'Boston.'}


def test_the_search_budget_can_cover_the_brief():
    """Three searches could not answer eight company facts plus the capabilities."""
    from battlecards import ai
    assert ai.ECONOMY['searches'] >= 6
    assert ai.STANDARD['searches'] >= ai.ECONOMY['searches']


def test_company_facts_are_searched_before_the_capabilities():
    from battlecards import ai
    prompt = ai._research_prompt('o9 Solutions', 'AttributeSmart', '')
    facts_at = prompt.index('headquarters')
    caps_at = prompt.index('For each capability')
    assert facts_at < caps_at, 'the cheap facts must not be crowded out'
    assert 'FIRST' in prompt


def test_one_definition_of_the_search_tool():
    from battlecards import ai
    assert not hasattr(ai, 'WEB_SEARCH_TOOL'), 'two definitions can drift apart'
    assert ai._search_tool(6)['max_uses'] == 6


class _SearchUsage:
    """A usage object carrying a server tool count."""

    def __init__(self, searches=None):
        self.input_tokens = 10
        self.output_tokens = 10
        self.cache_creation_input_tokens = 0
        self.cache_read_input_tokens = 0
        if searches is not None:
            self.server_tool_use = type('S', (), {'web_search_requests': searches})()


@pytest.mark.parametrize('searches,expected', [(0, 0), (4, 4), (None, 0)])
def test_the_search_count_is_reported(searches, expected):
    """Zero searches and a genuinely silent record must be distinguishable."""
    from battlecards import ai
    assert ai.searches_used(_SearchUsage(searches)) == expected


def test_a_truncated_brief_is_an_error_not_a_card_of_not_founds(monkeypatch):
    from battlecards import ai

    class FakeStream:
        text_stream = iter(['Partial brief'])

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get_final_message(self):
            return type('M', (), {'stop_reason': 'max_tokens', 'usage': _SearchUsage(2),
                                  'content': []})()

    class FakeClient:
        messages = type('M', (), {'stream': lambda self, **kw: FakeStream()})()

    monkeypatch.setattr(ai, 'available', lambda: True)
    monkeypatch.setattr(ai, '_client', lambda: FakeClient())
    events = list(ai.generate_events('o9 Solutions', 'AttributeSmart'))
    assert events[-1]['type'] == 'error'
    assert 'cut off' in events[-1]['message']
    assert not any(event['type'] == 'card' for event in events)


def test_a_run_with_no_search_says_so(monkeypatch):
    """Silent failure is the thing to avoid: the card would look researched."""
    from battlecards import ai

    class FakeStream:
        text_stream = iter(['A brief with no sources.'])

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get_final_message(self):
            return type('M', (), {'stop_reason': 'end_turn', 'usage': _SearchUsage(0),
                                  'content': []})()

    class FakeClient:
        messages = type('M', (), {'stream': lambda self, **kw: FakeStream()})()

    monkeypatch.setattr(ai, 'available', lambda: True)
    monkeypatch.setattr(ai, '_client', lambda: FakeClient())
    monkeypatch.setattr(ai, '_structure',
                        lambda *a, **k: {'meta': {}, 'snapshot': {}})
    events = list(ai.generate_events('o9 Solutions', 'AttributeSmart'))
    counts = [event for event in events if event['type'] == 'searches']
    assert counts and counts[0]['count'] == 0
    warning = [event for event in events
               if event['type'] == 'status' and 'no web search ran' in event['message']]
    assert warning, [event['type'] for event in events]


# ── the snapshot grid has to flow ───────────────────────────────────────────
# The facts above are sentences, not single words, and the grid used a fixed
# 0.52in row. The longer facts ran straight over the next row's label.

@pytest.mark.parametrize('competitor', sorted(attributesmart.COMPETITORS))
def test_no_company_fact_overruns_its_box(tmp_path, competitor):
    from pptx import Presentation
    from pptx.util import Emu
    from battlecards.brand import text_height

    card = attributesmart.card_for(competitor)
    deck = Presentation(service.build(card, str(tmp_path))['path'])
    slide = next(s for s in deck.slides
                 if any(sh.has_text_frame and 'Competitor snapshot' in sh.text_frame.text
                        for sh in s.shapes))

    # The left panel's text, top to bottom. Labels are the 6pt runs.
    boxes = []
    for shape in slide.shapes:
        if not shape.has_text_frame or not shape.text_frame.text.strip():
            continue
        if shape.left > Emu(int(deck.slide_width) // 2):
            continue                      # right panel, a bulleted list
        runs = [run for para in shape.text_frame.paragraphs for run in para.runs]
        if not runs or runs[0].font.size is None:
            continue
        boxes.append((int(shape.top), int(shape.height), shape.text_frame.text,
                      runs[0].font.size.pt, int(shape.width)))
    boxes.sort()

    for top, height, text, size, width in boxes:
        if size <= 6.5:
            continue                      # a label, one line by construction
        needed = text_height(text, width, size)
        assert needed <= height, (competitor, text[:40], needed, height)

    # A value's text must clear the next row's label. The label box itself sits a
    # hair inside its own value's offset by design, so only values are checked.
    for index, (top, height, text, size, width) in enumerate(boxes):
        if size <= 6.5:
            continue
        below = [box for box in boxes[index + 1:] if box[0] > top + 100]
        if not below:
            continue
        needed = text_height(text, width, size)
        assert top + needed <= below[0][0], (competitor, text[:40], below[0][2][:30])


def test_the_grid_shrinks_rather_than_spilling_off_the_panel():
    """Eight long facts still have to land inside the card."""
    card = attributesmart.card_for('o9 Solutions')
    long_fact = ('A deliberately long company fact that runs well past one line so '
                 'the grid has to either shrink the type or run out of room. ') * 2
    for field in ('headquarters', 'founded', 'employees', 'ownership', 'funding',
                  'target_segment', 'go_to_market', 'deployment'):
        card['snapshot'][field] = long_fact
    import tempfile
    with tempfile.TemporaryDirectory() as out:
        result = service.build(card, out)
    assert result['compatibility']['ok']


# ── teaching the builder ────────────────────────────────────────────────────
# Public research only reaches so far. This is the store the team owns, and the
# confidence tier on each claim decides whether a card may state it or has to
# turn it into a question.

def _claim(**over):
    base = {'competitor': 'o9 Solutions', 'ia_product': 'AttributeSmart',
            'kind': 'gap', 'claim': 'Attribute tagging is a services engagement.',
            'detail': 'Their engineer said so in a bake off.',
            'confidence': 'field', 'source': ''}
    base.update(over)
    return base


def test_a_claim_needs_a_competitor_a_kind_and_a_confidence():
    from battlecards import intel
    for missing in ('competitor', 'kind', 'confidence', 'claim'):
        with pytest.raises(ValueError):
            intel.normalize(_claim(**{missing: ''}))


def test_a_verified_claim_cannot_be_saved_without_its_source():
    """The tier that lets a card assert something is the tier that needs a link."""
    from battlecards import intel
    with pytest.raises(ValueError) as caught:
        intel.normalize(_claim(confidence='verified', source=''))
    assert 'source' in str(caught.value)
    ok = intel.normalize(_claim(confidence='verified',
                                source='https://o9solutions.com/news/'))
    assert ok['confidence'] == 'verified'


def test_an_unknown_tier_or_kind_is_refused():
    from battlecards import intel
    with pytest.raises(ValueError):
        intel.normalize(_claim(confidence='definitely'))
    with pytest.raises(ValueError):
        intel.normalize(_claim(kind='vibes'))


def test_a_taught_claim_is_sanitized_like_card_copy():
    from battlecards import intel
    entry = intel.normalize(_claim(claim='They lost the deal — badly.'))
    assert '—' not in entry['claim']


def test_a_claim_defaults_to_today_and_reads_a_given_date():
    from battlecards import intel
    import datetime
    assert intel.normalize(_claim())['as_of'] == datetime.date.today().isoformat()
    assert intel.normalize(_claim(as_of='2026-08-14'))['as_of'] == '2026-08-14'
    with pytest.raises(ValueError):
        intel.normalize(_claim(as_of='last August'))


def test_old_field_intel_is_flagged_for_a_recheck():
    from battlecards import intel
    import datetime
    fresh = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
    old = (datetime.date.today() - datetime.timedelta(days=400)).isoformat()
    assert not intel.is_stale({'as_of': fresh})
    assert intel.is_stale({'as_of': old})


def test_every_tier_states_what_a_card_may_do_with_it():
    from battlecards import intel
    for tier, spec in intel.CONFIDENCE.items():
        assert spec['rule'] and spec['label'], tier
    # Only the public tier may be asserted outright.
    assert intel.CONFIDENCE['verified']['needs_source'] is True
    assert intel.CONFIDENCE['field']['needs_source'] is False
    assert intel.CONFIDENCE['hearsay']['needs_source'] is False


def test_the_prompt_tells_claude_never_to_assert_hearsay():
    """The whole point. Unconfirmed intel has to reach the slide as a question."""
    from battlecards import intel
    block = intel.prompt_block('o9 Solutions', 'AttributeSmart', entries=[
        dict(intel.normalize(_claim(confidence='hearsay',
                                    claim='They are rewriting the planner.')),
             stale=False),
    ])
    assert 'HEARD SECOND HAND' in block
    assert 'Never assert it' in block
    assert 'question' in block


def test_the_prompt_carries_the_house_rule_on_pricing_and_customers():
    from battlecards import intel
    block = intel.prompt_block('o9 Solutions', '', entries=[
        dict(intel.normalize(_claim(kind='pricing',
                                    claim='They price per SKU per month.')),
             stale=False),
        dict(intel.normalize(_claim(kind='customer',
                                    claim='They run a large grocer in Australia.')),
             stale=False),
    ])
    assert 'Never print a competitor price' in block
    assert 'Do not name the account' in block


def test_a_stale_claim_reaches_the_prompt_as_a_question():
    from battlecards import intel
    block = intel.prompt_block('o9 Solutions', '', entries=[
        dict(intel.normalize(_claim()), stale=True)])
    assert 'STALE' in block
    assert 're-confirm' in block


def test_an_empty_store_leaves_the_prompt_untouched():
    from battlecards import intel
    assert intel.prompt_block('Nobody', '', entries=[]) == ''


def test_taught_claims_reach_the_system_prompt(monkeypatch):
    from battlecards import ai, intel
    monkeypatch.setattr(intel, 'listing', lambda *a, **k: [
        dict(intel.normalize(_claim(claim='They subcontract the taxonomy work.')),
             stale=False)])
    blocks = ai._system_prompt('AttributeSmart', 'o9 Solutions')
    joined = '\n'.join(block['text'] for block in blocks)
    assert 'subcontract the taxonomy work' in joined
    # The taught block must sit outside the cached prefix, or a new claim would
    # be served from yesterday's cache.
    cached = [block for block in blocks if block.get('cache_control')]
    assert len(cached) == 1
    assert 'subcontract' not in cached[0]['text']


def test_a_broken_intel_store_never_breaks_a_card(monkeypatch):
    """Generation matters more than the extra context, so failure is quiet."""
    from battlecards import ai, intel

    def explode(*args, **kwargs):
        raise RuntimeError('database gone')

    monkeypatch.setattr(intel, 'prompt_block', explode)
    blocks = ai._system_prompt('AttributeSmart', 'o9 Solutions')
    assert blocks and blocks[0]['text']


def test_a_committed_seed_is_read_and_a_bad_one_is_skipped(tmp_path, monkeypatch):
    from battlecards import intel
    (tmp_path / 'rivals.json').write_text(json.dumps({'intel': [
        _claim(claim='A good committed claim.'),
        _claim(claim='A claim with no tier.', confidence=''),
    ]}))
    monkeypatch.setattr(intel, 'SEED_DIR', str(tmp_path))
    rows = intel.seeds()
    assert [row['claim'] for row in rows] == ['A good committed claim.']
    assert rows[0]['seed'] is True


def test_a_committed_claim_cannot_be_retired_from_the_browser():
    """Editing it has to go through a reviewed commit, not a click."""
    from battlecards import intel
    with pytest.raises(ValueError) as caught:
        intel.retire('seed:rivals:0')
    assert 'content/intel' in str(caught.value)


def test_the_export_drops_the_database_only_fields(monkeypatch):
    from battlecards import intel
    monkeypatch.setattr(intel, 'listing', lambda *a, **k: [
        dict(intel.normalize(_claim()), id=7, retired=False, seed=False,
             stale=False, created_at='2026-09-01T00:00:00'),
        dict(intel.normalize(_claim(claim='A seed.')), id='seed:x:0', seed=True),
    ])
    rows = intel.export()['intel']
    assert len(rows) == 1, 'a committed seed must not be exported back'
    assert set(rows[0]) == {'competitor', 'ia_product', 'kind', 'claim', 'detail',
                            'confidence', 'source', 'author', 'as_of'}


def test_the_teach_page_renders_and_links_from_the_builder(client):
    page = client.get('/intel')
    assert page.status_code == 200
    body = page.data.decode()
    for tier in ('Verified in public', 'Seen in a deal', 'Heard second hand'):
        assert tier in body
    assert '/intel' in client.get('/').data.decode()


def test_adding_a_claim_without_a_database_says_where_to_put_it(client, monkeypatch):
    import app as flask_app
    monkeypatch.setattr(flask_app.battlecard_intel, 'enabled', lambda: False)
    response = client.post('/api/intel', json=_claim())
    assert response.status_code == 503
    assert 'content/intel' in response.get_json()['error']


def test_a_bad_claim_comes_back_as_a_problem_not_a_silent_drop(client, monkeypatch):
    import app as flask_app
    monkeypatch.setattr(flask_app.battlecard_intel, 'enabled', lambda: True)
    monkeypatch.setattr(flask_app.battlecard_intel, 'init', lambda force=False: True)
    response = client.post('/api/intel', json={'claims': [
        _claim(confidence='verified', source='')]})
    assert response.status_code == 400
    assert 'source' in response.get_json()['failed'][0]['problem']


def test_structuring_a_note_refuses_without_a_credential(client, monkeypatch):
    import app as flask_app
    monkeypatch.setattr(flask_app.battlecard_ai, 'available', lambda: False)
    response = client.post('/api/intel/extract', json={'text': 'They lost a deal.'})
    assert response.status_code == 503
    assert 'one at a time' in response.get_json()['error']


def test_a_note_is_split_into_claims_for_review(monkeypatch):
    """Extraction proposes. Nothing is saved until the person approves it."""
    from battlecards import ai

    body = json.dumps([
        {'kind': 'gap', 'claim': 'Tagging is a services engagement.',
         'detail': 'Their engineer said so.', 'confidence': 'field', 'source': ''},
        {'kind': 'pricing', 'claim': 'They price per SKU per month.',
         'detail': 'Seen on the quote.', 'confidence': 'field', 'source': ''},
        {'kind': 'gap', 'claim': 'No source, claims to be verified.',
         'detail': '', 'confidence': 'verified', 'source': ''},
    ])

    class FakeStream:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get_final_message(self):
            return type('M', (), {
                'stop_reason': 'end_turn', 'usage': _SearchUsage(0),
                'content': [type('B', (), {'type': 'text', 'text': body})()]})()

    class FakeClient:
        messages = type('M', (), {'stream': lambda self, **kw: FakeStream()})()

    monkeypatch.setattr(ai, '_client', lambda: FakeClient())
    result = ai.extract_intel('a note', 'o9 Solutions', 'AttributeSmart', 'me')
    assert [row['kind'] for row in result['proposals']] == ['gap', 'pricing']
    assert result['proposals'][0]['competitor'] == 'o9 Solutions'
    assert result['proposals'][0]['author'] == 'me'
    # The third claimed to be verified with no link, so it is surfaced, not kept.
    assert len(result['rejected']) == 1
    assert 'source' in result['rejected'][0]['problem']


@pytest.mark.parametrize('wrapped', [
    '[{"kind": "gap"}]',
    '```json\n[{"kind": "gap"}]\n```',
    'Here are the claims:\n[{"kind": "gap"}]',
    '{"claims": [{"kind": "gap"}]}',
    '{"kind": "gap"}',
])
def test_the_claim_list_survives_model_drift(wrapped):
    from battlecards import ai
    assert ai._parse_intel_json(wrapped) == [{'kind': 'gap'}]


def test_teaching_never_guesses_a_higher_confidence():
    """The instruction that keeps a rumour from becoming a stated fact."""
    from battlecards import ai
    assert 'choose hearsay' in ai.TEACH_SYSTEM
    assert 'Overstating confidence' in ai.TEACH_SYSTEM

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

    def fake(competitor, product, depth, notes):
        yield {'type': 'status', 'step': 'research', 'message': 'searching'}
        yield {'type': 'card', 'card': {'meta': {'competitor': competitor}},
               'curated': False, 'research': 'brief'}

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

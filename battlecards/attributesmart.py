"""AttributeSmart battlecards: the IA side in depth, competitors only where sourced.

The Impact Analytics content here comes from the AttributeSmart NRF 2026 deck, so
it is specific and citable internally. The competitor content comes from public
material, and every claim carries its source. Where the public record says
nothing, the rating is `unknown` and the seller is told to research it rather than
handed a guess. That asymmetry is deliberate: a battlecard that overstates a
rival's gap loses the deal the moment the buyer corrects it.

Category note. AttributeSmart *generates* attributes from images, labels and text.
The planning suites in COMPETITORS mostly *consume* attributes. Oracle is the one
named vendor shipping a directly competing extraction product, and its public
material describes text input rather than images. Read `DIRECT_RIVALS` for the
vendors that actually compete on generation.
"""

from __future__ import annotations

import copy

IA_CITATION = 'IA AttributeSmart NRF 2026 deck'

# ─── The Impact Analytics side ──────────────────────────────────────────────────

MECHANISM = {
    'image': 'CNN models take multiple product images, assign weights and biases, '
             'and identify attributes from the image itself.',
    'ocr': 'OCR reads packaging and label images, so attributes already printed on '
           'the pack never get retyped.',
    'text': 'NLP parses existing product descriptions and e-commerce copy, then '
            'harmonises the result when two sources disagree.',
    'taxonomy': 'A pre-trained library of 10,000 plus fashion and home attributes, '
                'curated by retail experts, plus 400 plus food tags maintained '
                'against FDA packaging guidance.',
    'derived': 'Derived attributes go beyond what the pack states, using FDA '
               'labelling guidance and external data to infer diet, allergen, '
               'wellness and clean label attributes.',
    'discovery': 'Synonym, SEO and trend modules add the words shoppers actually '
                 'search, not only the words the supplier supplied.',
    'workflow': 'Reviews are prioritised by model confidence, so merchants spend '
                'their time on the tags the model ranks as least certain.',
    'integration': 'APIs and file exports push into PIM, MDM, ERP, CMS and '
                   'e-commerce systems, or a single API serves the attributes.',
}

PROOF_POINTS = [
    {'stat': '60%', 'label': 'Cost saving on manual attribution',
     'detail': 'Automating attribute creation and management cut man hours on a '
               '500,000 image catalogue.',
     'source': IA_CITATION},
    {'stat': '65% to 96%', 'label': 'Attribute accuracy',
     'detail': 'Accuracy moved from 65 percent to 96 percent after the AI models '
               'took over tagging.',
     'source': IA_CITATION},
    {'stat': '5-10%', 'label': 'AOV uplift',
     'detail': 'Better product discovery raised average order value.',
     'source': IA_CITATION},
    {'stat': '5-6%', 'label': 'E-commerce search conversion',
     'detail': 'Richer attributes and synonyms improved on-site search conversion.',
     'source': IA_CITATION},
]

# What a buyer actually feels, and which the planning suites do not fix on their own.
PAIN_POINTS = [
    'More than 70 percent of attributes carry at least one error.',
    'Merchants spend 15 minutes or more per product entering and correcting data.',
    'Over 45 percent of data goes unused because it is neither clean nor standardised.',
]

# ─── Capabilities worth comparing for attribution specifically ──────────────────
# `ia` ratings are all supported by the deck. Competitor ratings live per vendor.

CAPABILITIES = [
    ('Attribute generation from product images', 'strong'),
    ('OCR extraction from packaging and labels', 'strong'),
    ('NLP extraction from product descriptions', 'strong'),
    ('Pre-trained attribute library at retail depth', 'strong'),
    ('Derived attributes beyond on-pack facts', 'strong'),
    ('Synonym and search term tagging', 'strong'),
    ('Trend and SEO driven attribute capture', 'strong'),
    ('Confidence scored review workflow', 'strong'),
    ('Custom taxonomy and client mapping', 'strong'),
    ('Push into PIM, MDM and e-commerce', 'strong'),
    ('Time to a tagged catalogue', 'strong'),
    ('Attributes feeding downstream planning', 'strong'),
]

COMMON_TALK_TRACK = {
    'positioning': 'For retailers whose product data blocks every downstream '
                   'decision, AttributeSmart generates deep, standardised attributes '
                   'from images, labels and text, so forecasting, assortment and '
                   'search all run on data merchants trust.',
    'elevator': 'AttributeSmart reads your product images, your pack labels and your '
                'descriptions, then writes back a standardised attribute set. '
                'Accuracy went from 65 percent to 96 percent at one retailer, and '
                'manual attribution cost dropped 60 percent.',
    'discovery_open': 'How many minutes does a merchant spend per product today '
                      'entering and correcting attributes?',
    'trap': 'Ask where their attributes come from when a supplier sends an image '
            'and nothing else.',
}

COMMON_DOS = [
    'Lead with the attribute error rate the buyer already measures.',
    'Separate generating attributes from consuming them. That line is the deal.',
    'Offer the two week proof on their own catalogue, 100,000 products.',
    'Name the downstream decision the bad data is breaking, then price that.',
    'Cite the source for every number, including ours.',
]

COMMON_DONTS = [
    'Do not claim a rival lacks a capability you have not verified on the call.',
    'Do not position against the planning suite. Most of these deals sit alongside one.',
    'Do not quote competitor pricing or roadmap.',
    'Do not send this card outside Impact Analytics.',
    'Do not present a comparison row marked Unclear as though it were a gap.',
]

COMMON_NEXT_STEPS = [
    'Run the two week proof: 100,000 products from their own catalogue.',
    'Agree the accuracy metric and the readout date before the test starts.',
    'Confirm which downstream system consumes the attributes first, PIM or planning.',
]

HOW_TO_USE = [
    'Read the mechanism slide before the call. The technical detail is the wedge.',
    'Establish whether they generate attributes or only consume them.',
    'Use the matrix only when the buyer asks for a direct comparison.',
    'Treat every Unclear rating as a question to ask, never as a gap to assert.',
    'Log what the buyer confirms, so the next card carries fact instead of prompt.',
]

# ─── Competitors named by the team ──────────────────────────────────────────────
# `strengths` and `claim` paraphrase public material and carry a source. `gaps`
# state what the public record does NOT claim, phrased so a seller asks rather
# than asserts. Ratings are `unknown` wherever the record is silent.

COMPETITORS = {
    'Oracle Retail': {
        # Company facts, sourced by hand. A blank field is not an oversight: it
        # means nothing was sourced, so the researcher fills it rather than the
        # deck asserting it. See FACTS_NOTE below.
        'facts': {
            'headquarters': 'A division of Oracle Corporation, not a standalone '
                            'vendor. Take the corporate address from Oracle '
                            'investor relations rather than a data broker.',
            'employees': 'Not published at division level. Oracle does not break '
                         'out Retail headcount, so do not quote one.',
            'ownership': 'Public. A business unit of Oracle Corporation, NYSE ORCL.',
            'funding': 'No round to quote. Funded from Oracle operations.',
            'target_segment': 'Enterprise retailers, sold inside the Oracle Retail suite.',
            'deployment': 'Cloud services, per Oracle\'s own Merchandising Cloud '
                          'Services naming.',
            'notable_customers': 'Oracle publishes retail references on its own site. '
                                 'Cite an Oracle page, not a tracker database, before '
                                 'naming a retailer on a call.',
        },
        'theme': 'Their extraction reads text. Lead with the image and label inputs their public material never claims.',
        'category': 'Enterprise retail suite with a dedicated attribute extraction product',
        'claim': 'Machine learning extracts item attributes from free-form product '
                 'descriptions and normalises the values, correcting short forms, '
                 'misspellings and inconsistencies.',
        'wedge': 'Their extraction reads descriptions. Ask what happens to a product '
                 'that arrives as an image and a pack shot with no usable copy.',
        'strengths': [
            'The only vendor on this list shipping a named attribute extraction '
            'product, so attribution is a funded roadmap item.',
            'Extracted attributes feed demand transference, customer decision trees '
            'and advanced clustering inside AI Foundation.',
            'Enterprise footprint and an existing data estate in most large retailers.',
        ],
        'gaps': [
            'Public material describes extraction from free-form descriptions. It '
            'does not claim image or label based extraction. Confirm on the call.',
            'No published attribute library depth for fashion or food. Ask for the '
            'number.',
            'No published synonym, SEO or trend attribute capability. Ask how search '
            'terms reach the catalogue.',
        ],
        'ratings': {
            'NLP extraction from product descriptions': 'strong',
            'Attributes feeding downstream planning': 'strong',
        },
        'objections': [
            {'objection': 'Oracle already extracts our attributes.',
             'response': 'Ask which inputs it reads. If the answer is descriptions, '
                         'the gap is every product that arrives as an image or a pack '
                         'shot. Offer to tag that subset in two weeks.',
             'proof': 'A retailer moved accuracy from 65 percent to 96 percent once '
                      'image and label inputs were included. ' + IA_CITATION},
            {'objection': 'We want one vendor for planning and attribution.',
             'response': 'AttributeSmart writes back into the PIM and the planning '
                         'stack, so the attributes improve without replacing either. '
                         'Price the margin the better data unlocks.',
             'proof': 'Integration into PIM, MDM, ERP and CMS is standard. ' + IA_CITATION},
        ],
        'landmines': [
            {'question': 'How does the model attribute a product that arrives with '
                         'images and no description?',
             'why': 'Text-only extraction has no answer to an image-first catalogue.',
             'listen_for': 'A manual process, or a supplier chase.'},
            {'question': 'How many attributes does the pre-trained library hold for '
                         'your categories?',
             'why': 'Library depth separates a real taxonomy from a field mapper.',
             'listen_for': 'A number in the hundreds, or no number at all.'},
            {'question': 'Who adds the words shoppers actually search but suppliers '
                         'never send?',
             'why': 'Synonym and trend tagging is a discovery capability, not an '
                    'extraction one.',
             'listen_for': 'The e-commerce team doing it by hand.'},
        ],
        'sources': [
            {'label': 'Oracle Retail Attribute Extraction',
             'url': 'https://www.oracle.com/industries/retail/products/attribute-extraction/'},
            {'label': 'Oracle Retail AI and Analytics',
             'url': 'https://www.oracle.com/retail/ai-analytics/'},
        ],
    },
    'Blue Yonder': {
        'facts': {
            'headquarters': 'Scottsdale, Arizona.',
            'founded': 'Founded in 1985 as JDA Software. Renamed Blue Yonder in '
                       'February 2020.',
            'employees': 'Trackers disagree and Panasonic does not break out the '
                         'figure. Do not quote a headcount.',
            'ownership': 'Owned by Panasonic since 2021, at 8.5 billion dollars '
                         'including debt, per Panasonic investor relations.',
            'funding': 'No venture round to quote. Panasonic funds it as a subsidiary.',
            'target_segment': 'Retail and supply chain, enterprise scale.',
            'recent_moves': [
                'Panasonic has said it is considering listing its supply chain '
                'business with Blue Yonder at the centre. The reporting dates from '
                '2022 and no completion is confirmed, so treat it as unresolved and '
                'check the position before raising it.',
            ],
        },
        'theme': 'They buy attribute quality from a content network. Lead with the private label share no network covers.',
        'category': 'Retail and supply chain suite, product content through partnership',
        'claim': 'A strategic partnership with Syndigo brings GS1 aligned product '
                 'content, validated attributes, standardised images and accurate '
                 'dimensions into Blue Yonder planning and execution.',
        'wedge': 'They source attribute quality from a content network. Ask what '
                 'covers the private label and long tail items no network carries.',
        'strengths': [
            'Syndigo partnership supplies GS1 aligned, validated attributes and '
            'standardised images, announced at ICON 2026.',
            'One update in Syndigo cascades to every partner in the Blue Yonder '
            'Network, which is real operational leverage.',
            'Validated attributes and images feed Space Planning for planogram '
            'creation, optimisation and compliance.',
        ],
        'gaps': [
            'The partnership supplies attributes from a content network. It is not '
            'described as generating attributes from your own images. Confirm this.',
            'Network content covers branded, GS1 registered items best. Ask how '
            'private label and long tail products get attributed.',
            'No published derived attribute capability, so diet, allergen and '
            'wellness inference is worth probing.',
        ],
        'ratings': {
            'Pre-trained attribute library at retail depth': 'partial',
            'Push into PIM, MDM and e-commerce': 'strong',
            'Attributes feeding downstream planning': 'strong',
        },
        'objections': [
            {'objection': 'Syndigo already gives us validated attributes.',
             'response': 'Syndigo is strong on GS1 registered branded items. Ask what '
                         'share of the assortment is private label. That share is '
                         'where AttributeSmart earns its place.',
             'proof': 'A 500,000 image catalogue tagged with 50 plus attribute types. '
                      + IA_CITATION},
            {'objection': 'We are consolidating on Blue Yonder.',
             'response': 'Keep consolidating. AttributeSmart feeds the attributes in '
                         'rather than competing for the planning seat.',
             'proof': 'Attributes flow to ForecastSmart, PlanSmart, AssortSmart and '
                      'InventorySmart the same way. ' + IA_CITATION},
        ],
        'landmines': [
            {'question': 'What share of your assortment is private label, and where '
                         'do those attributes come from?',
             'why': 'Content networks are thinnest exactly where private label lives.',
             'listen_for': 'A supplier template or a spreadsheet.'},
            {'question': 'When a supplier sends an image and a one line description, '
                         'who fills the other forty fields?',
             'why': 'It exposes the manual step behind a network feed.',
             'listen_for': 'A named team, or an offshore vendor.'},
            {'question': 'Can you infer diet, allergen and wellness attributes that '
                         'are not printed on the pack?',
             'why': 'Derived attribution is a different capability from validation.',
             'listen_for': 'Only what the label states.'},
        ],
        'sources': [
            {'label': 'Syndigo and Blue Yonder partnership',
             'url': 'https://syndigo.com/news/syndigo-blue-yonder-trusted-product-data-partnership/'},
            {'label': 'Blue Yonder and Syndigo, press release',
             'url': 'https://www.businesswire.com/news/home/20260519898378/en/Blue-Yonder-and-Syndigo-Partner-to-Bring-Trusted-Product-Data-to-Supply-Chain-Planning-and-Execution'},
            {'label': 'Panasonic investor relations, Blue Yonder acquisition',
             'url': 'https://holdings.panasonic/global/corporate/investors/pdf/en210423-1.pdf'},
        ],
    },
    'RELEX Solutions': {
        'facts': {
            'headquarters': 'Helsinki, Finland.',
            'founded': 'Founded in 2005 by Mikko Karkkainen, Johanna Smaros and '
                       'Michael Falck.',
            'employees': 'About 2,355 per PitchBook in July 2026. A tracker figure, '
                         'so do not present it as RELEX published.',
            'ownership': 'Private. Blackstone Growth led a 500 million euro round at '
                         'a 5 billion euro valuation, confirmed on RELEX\'s own '
                         'newsroom.',
            'funding': 'The 500 million euro Blackstone Growth round is on RELEX\'s '
                       'own newsroom. PitchBook puts total raised at 811 million '
                       'dollars, which is a tracker figure.',
            'target_segment': 'Grocery and retail demand and supply planning.',
        },
        'theme': 'Their attributes exist to serve a forecast. Lead with catalogue grade depth, forty fields not four.',
        'category': 'Retail planning and replenishment platform with a product attribute AI agent',
        'claim': 'The Product Attribute AI agent identifies relevant product '
                 'attributes and automatically finds best matched reference products '
                 'for new product introductions, continuously enriching and '
                 'validating product data.',
        'wedge': 'Their agent exists to make a forecast work. Ask whether the same '
                 'attributes are good enough to publish on the website.',
        'strengths': [
            'The Product Attribute AI agent gives day one forecasts for new products '
            'by matching reference products automatically.',
            'Agents run with human in the loop governance, and attribute assignment '
            'is explicitly listed as a low oversight routine decision.',
            'Enriched attributes feed assortment, pricing and promotion decisions '
            'inside one platform.',
        ],
        'gaps': [
            'The agent is positioned for forecasting and reference matching. It is '
            'not described as generating a catalogue grade attribute set. Verify.',
            'Image recognition in the RELEX ecosystem appears through a planogram '
            'partner, not product attribution. Ask what reads product images.',
            'No published attribute library depth, synonym tagging or SEO attribute '
            'capability. Ask how e-commerce search benefits.',
        ],
        'ratings': {
            'Pre-trained attribute library at retail depth': 'unknown',
            'Attributes feeding downstream planning': 'strong',
            'Confidence scored review workflow': 'partial',
        },
        'objections': [
            {'objection': 'RELEX already has a product attribute agent.',
             'response': 'Ask which job the attributes serve. Reference matching for '
                         'a forecast needs a handful of attributes. A product page '
                         'needs forty. Offer to show that gap on their catalogue.',
             'proof': 'A 10,000 plus attribute library for fashion and home. '
                      + IA_CITATION},
            {'objection': 'We do not want another data vendor.',
             'response': 'AttributeSmart is upstream of RELEX, not beside it. Better '
                         'attributes make their forecast agent better.',
             'proof': 'Attributes become the basis of forecasting and allocation '
                      'downstream. ' + IA_CITATION},
        ],
        'landmines': [
            {'question': 'Are the attributes driving your forecast the same ones on '
                         'your product pages?',
             'why': 'Planning attributes and catalogue attributes are rarely the same '
                    'set, and the gap is usually manual.',
             'listen_for': 'Two systems, or two teams.'},
            {'question': 'What in your stack reads a product image?',
             'why': 'Planogram image recognition is not product attribution.',
             'listen_for': 'A planogram tool, or nothing.'},
            {'question': 'How does a new product get attributed when there is no '
                         'comparable reference product?',
             'why': 'Reference matching degrades exactly where novelty is highest.',
             'listen_for': 'A planner picking a reference by hand.'},
        ],
        'sources': [
            {'label': 'RELEX AI agents for retail',
             'url': 'https://www.relexsolutions.com/resources/introducing-relex-ai-agents-for-retail/'},
            {'label': 'RELEX demand planning',
             'url': 'https://www.relexsolutions.com/solutions/demand-planning-software/'},
            {'label': 'RELEX newsroom, Blackstone Growth round',
             'url': 'https://www.relexsolutions.com/news/relex-solutions-raises-500m-in-blackstone-led-funding-round-at-5bn-valuation/'},
        ],
    },
    'o9 Solutions': {
        'facts': {
            'headquarters': 'Dallas, Texas.',
            'founded': 'Founded in 2009 by Sanjiv Sidhu and Chakri Gottemukkala.',
            'employees': 'Trackers range from roughly 1,200 to 3,300, so do not '
                         'quote a precise headcount.',
            'ownership': 'Private. KKR, General Atlantic including BeyondNetZero, '
                         'and Generation Investment Management are investors.',
            'funding': '295 million dollars in January 2022 at a 2.7 billion dollar '
                       'valuation, then 116 million dollars in July 2023 at a 3.7 '
                       'billion dollar valuation. Both are on o9\'s own newsroom.',
            'target_segment': 'Large enterprise integrated business planning across '
                              'verticals, retail among them.',
        },
        'theme': "They consume attributes. Lead with who produces them today, and what that team's error rate is.",
        'category': 'Planning platform that consumes attributes through a knowledge graph',
        'claim': 'The Enterprise Knowledge Graph connects customer behaviour, product '
                 'attributes, financial targets and execution constraints, and plans '
                 'can be built and analysed by attribute.',
        'wedge': 'The knowledge graph is only as good as the attributes fed into it. '
                 'Ask who creates those attributes today.',
        'strengths': [
            'Planning by attribute is native, including price bands, fabric type and '
            'innovation versus core.',
            'The knowledge graph ties attributes to behaviour, targets and '
            'constraints in one model.',
            'Granularity down to SKU, product and attribute level for analysis.',
        ],
        'gaps': [
            'Public material describes consuming and planning by attributes, not '
            'generating them. Confirm where their attributes originate.',
            'No published image, OCR or label extraction capability.',
            'No published attribute library, synonym tagging or review workflow for '
            'attribute quality.',
        ],
        'ratings': {
            'Attributes feeding downstream planning': 'strong',
        },
        'objections': [
            {'objection': 'Our knowledge graph already handles attributes.',
             'response': 'The graph consumes attributes. Ask which team produces them '
                         'and what the error rate is. That is the input problem '
                         'AttributeSmart solves.',
             'proof': 'More than 70 percent of attributes carry at least one error '
                      'before automation. ' + IA_CITATION},
            {'objection': 'We are mid implementation and cannot add scope.',
             'response': 'Attribution runs in parallel and improves what the '
                         'implementation is being fed. Two weeks, 100,000 products, '
                         'no planning change.',
             'proof': 'Two week build for 100,000 plus products. ' + IA_CITATION},
        ],
        'landmines': [
            {'question': 'Which team produces the attributes your knowledge graph '
                         'runs on, and what is their error rate?',
             'why': 'It moves the conversation from the model to its inputs.',
             'listen_for': 'No owner, or no measurement.'},
            {'question': 'How long does it take to add a new attribute across the '
                         'whole catalogue?',
             'why': 'Retrofitting an attribute by hand is a months long job.',
             'listen_for': 'An answer measured in quarters.'},
            {'question': 'Can you plan by an attribute you do not yet capture?',
             'why': 'The honest answer is no, which is the whole pitch.',
             'listen_for': 'A request to see how we would capture it.'},
        ],
        'sources': [
            {'label': 'o9 merchandise planning',
             'url': 'https://o9solutions.com/solutions/merchandise-planning'},
            {'label': 'o9 apparel, footwear and luxury planning',
             'url': 'https://o9solutions.com/industries/retail/apparel-footwear-luxury'},
            {'label': 'o9 newsroom, 295 million dollar round',
             'url': 'https://o9solutions.com/news/o9-solutions-raises-295-million-to-grow-its-ai-powered-integrated-business-planning-platform'},
            {'label': 'o9 newsroom, 3.7 billion dollar valuation',
             'url': 'https://o9solutions.com/news/existing-investors-double-down-on-o9-solutions-growth-with-incremental-investment-at-3-7-billion-valuation'},
        ],
    },
}

# Vendors that compete on generating attributes, which is AttributeSmart's actual
# job. The planning suites above mostly consume attributes instead.
DIRECT_RIVALS = [
    {'name': 'Lily AI', 'note': 'Product attribute platform enriching titles, '
                                'descriptions, schema, image alt text and catalogue '
                                'attributes, strongest in fashion and beauty.',
     'url': 'https://www.lily.ai/product-attribution/'},
    {'name': 'Vue.ai', 'note': 'Product tagging and catalogue automation bundled with '
                               'search, recommendations and on-model imagery.',
     'url': 'https://vue.ai/'},
    {'name': 'Pixyle AI', 'note': 'AI product tagging and automated attribute '
                                  'generation for fashion.',
     'url': 'https://www.pixyle.ai/solutions/product-tagging'},
    {'name': 'Syndigo', 'note': 'PIM, MDM and content syndication, the content '
                                'network behind the Blue Yonder partnership.',
     'url': 'https://syndigo.com/'},
    {'name': 'Salsify', 'note': 'Product experience management with digital shelf '
                                'analytics and AI content optimisation.',
     'url': 'https://www.salsify.com/'},
    {'name': 'Akeneo', 'note': 'PIM with AI enrichment, common as the system of record '
                               'AttributeSmart writes into.',
     'url': 'https://www.akeneo.com/'},
]


FACTS_NOTE = """A blank field in `facts` is deliberate.

It means nothing was sourced for that competitor, so the researcher fills it and
the deck stays quiet, rather than the card asserting a figure nobody checked. A
filled field carries where it came from inside the sentence, and says so plainly
when the number is a third party tracker rather than the company's own word."""

_SNAPSHOT_FIELDS = ('headquarters', 'founded', 'employees', 'ownership', 'funding',
                    'target_segment', 'go_to_market', 'deployment',
                    'notable_customers')


def _snapshot_for(profile: dict) -> dict:
    """Company facts for the snapshot slide, from the hand sourced `facts` block."""
    facts = profile.get('facts') or {}
    snapshot = {field: facts.get(field) or '' for field in _SNAPSHOT_FIELDS}
    if not snapshot['notable_customers']:
        snapshot['notable_customers'] = ('Research and cite before naming anyone '
                                         'on a call.')
    snapshot['recent_moves'] = list(facts.get('recent_moves') or []) + [
        'Category: %s' % profile['category'],
        'Their public claim: %s' % profile['claim'],
        'Refresh this quarterly. Every line needs a dated source.',
    ]
    return snapshot


def card_for(competitor: str, owner: str = '', date_label: str = '') -> dict:
    """Assemble a full AttributeSmart battlecard payload for one competitor."""
    profile = COMPETITORS.get(competitor)
    if profile is None:
        raise KeyError('No AttributeSmart profile for %r. Known: %s'
                       % (competitor, ', '.join(sorted(COMPETITORS))))

    comparison = []
    for capability, ia_rating in CAPABILITIES:
        comparison.append({
            'capability': capability,
            'ia': ia_rating,
            'competitor': profile['ratings'].get(capability, 'unknown'),
            'note': _note_for(capability, profile),
        })

    return {
        'meta': {
            'competitor': competitor,
            'competitor_category': profile['category'],
            'ia_product': 'AttributeSmart',
            'solution': 'data_intelligence',
            'owner': owner,
            'audience': 'Sales and solution consulting',
            'date': date_label,
            'distribution': 'internal',
            'headline': 'AttributeSmart generates the attributes. %s consumes them.'
                        % competitor,
            'win_theme': profile.get('theme') or profile['wedge'],
        },
        'how_to_use': list(HOW_TO_USE),
        'snapshot': _snapshot_for(profile),
        'positioning': {
            'their_claim': profile['claim'],
            'our_claim': MECHANISM['image'] + ' ' + MECHANISM['ocr'] + ' '
                         + MECHANISM['text'],
            'wedge': profile['wedge'],
        },
        'their_strengths': list(profile['strengths']),
        'their_weaknesses': list(profile['gaps']),
        'our_advantages': [
            {'title': 'Three inputs, not one',
             'detail': MECHANISM['image'] + ' ' + MECHANISM['ocr'],
             'proof': 'Accuracy of 65 to 96 percent once all three inputs ran. '
                      + IA_CITATION},
            {'title': 'A library, not a mapper',
             'detail': MECHANISM['taxonomy'] + ' ' + MECHANISM['derived'],
             'proof': '10,000 plus attributes for fashion and home, 400 plus food '
                      'tags. ' + IA_CITATION},
            {'title': 'Built for the merchant, not the model',
             'detail': MECHANISM['workflow'] + ' ' + MECHANISM['integration'],
             'proof': '60 percent cost saving on manual attribution. ' + IA_CITATION},
        ],
        'comparison': comparison,
        'objections': list(profile['objections']),
        'landmines': list(profile['landmines']),
        'discovery': [
            {'theme': 'Where attributes come from', 'questions': [
                'Which team creates a new product attribute today?',
                'How many minutes per product does that take?',
                'What happens when a supplier sends an image and nothing else?']},
            {'theme': 'Data quality', 'questions': [
                'What share of your attributes carry at least one error?',
                'How much of your product data goes unused because it is not '
                'standardised?',
                'Who notices first when an attribute is wrong?']},
            {'theme': 'Downstream cost', 'questions': [
                'Which decision breaks first when attributes are thin, forecast or '
                'search?',
                'What did poor product discovery cost you in conversion last '
                'quarter?']},
        ],
        'proof_points': copy.deepcopy(PROOF_POINTS),
        'talk_track': dict(COMMON_TALK_TRACK),
        'dos': list(COMMON_DOS),
        'donts': list(COMMON_DONTS),
        'pricing': {
            'ia_model': 'Subscription scoped by category and catalogue size, with '
                        'services scoped per phase. Confirm the current model with '
                        'deal desk before you quote.',
            'competitor_model': 'Record only what the buyer states or the vendor '
                                'publishes. Nothing here is sourced.',
            'notes': [
                'Never quote a rival price you cannot source.',
                'Price the cost of staying: manual hours plus the margin the bad '
                'data is losing.',
            ],
        },
        'next_steps': list(COMMON_NEXT_STEPS),
        'resources': list(profile['sources']) + [
            {'label': 'AttributeSmart product page',
             'url': 'https://www.impactanalytics.ai/solutions/product-tagging'},
        ],
        'options': {'include_notes': True, 'sanitize_copy': True},
    }


def _note_for(capability: str, profile: dict) -> str:
    """The line a seller says for this row, tuned to the competitor's rating."""
    rating = profile['ratings'].get(capability, 'unknown')
    if rating == 'strong':
        return 'Match. Move to depth and inputs rather than the capability itself.'
    if rating == 'partial':
        return 'Partial. Ask what it does not cover, then scope that.'
    return 'Not claimed publicly. Ask the question, do not assert the gap.'


def all_cards(owner: str = '', date_label: str = '') -> dict:
    """Every AttributeSmart battlecard, keyed by competitor."""
    return {name: card_for(name, owner, date_label) for name in COMPETITORS}

"""Starter content for the battlecard builder.

Two rules shaped this file. First, everything about Impact Analytics comes from
the product portfolio and the brand guide. Second, nothing here asserts a fact
about a competitor. Presets supply the scaffolding a seller fills in: the
capabilities worth comparing, the questions worth asking and the sections a
finished card needs. Claims about a rival stay the seller's to research and
source.
"""

from __future__ import annotations

from .brand import PRODUCT_SOLUTIONS, SOLUTION_LABELS

# ─── Impact Analytics portfolio ─────────────────────────────────────────────────

PRODUCT_CATALOG = [
    {'name': 'ItemSmart', 'solution': 'merchandising',
     'blurb': 'Item level planning across the merchandise hierarchy.'},
    {'name': 'PlanSmart', 'solution': 'merchandising',
     'blurb': 'Merchandise financial planning tied to the assortment.'},
    {'name': 'AssortSmart', 'solution': 'merchandising',
     'blurb': 'Assortment planning by store cluster and channel.'},
    {'name': 'SizeSmart', 'solution': 'merchandising',
     'blurb': 'Size and pack optimisation down to the store.'},
    {'name': 'StoreSmart', 'solution': 'merchandising',
     'blurb': 'Store clustering and localised plans.'},
    {'name': 'InventorySmart', 'solution': 'inventory_replenishment',
     'blurb': 'Allocation and replenishment driven by demand forecasts.'},
    {'name': 'ForecastSmart', 'solution': 'inventory_replenishment',
     'blurb': 'Demand forecasting across the item and location grid.'},
    {'name': 'SourceSmart', 'solution': 'inventory_replenishment',
     'blurb': 'Sourcing and buy planning against the inventory plan.'},
    {'name': 'PriceSmart', 'solution': 'pricing_promotions',
     'blurb': 'Price optimisation across regular, promo and clearance.'},
    {'name': 'PromoSmart', 'solution': 'pricing_promotions',
     'blurb': 'Promotion planning and post event measurement.'},
    {'name': 'MarkSmart', 'solution': 'pricing_promotions',
     'blurb': 'Markdown optimisation that protects margin and sell through.'},
    {'name': 'AttributeSmart', 'solution': 'data_intelligence',
     'blurb': 'Attribute enrichment that feeds every downstream model.'},
    {'name': 'CortexEye', 'solution': 'data_intelligence',
     'blurb': 'Computer vision and market intelligence on product data.'},
    {'name': 'MondaySmart', 'solution': 'data_intelligence',
     'blurb': 'Weekly business review reporting for merchant teams.'},
]

# ─── Capabilities worth comparing, by solution ──────────────────────────────────

CAPABILITY_LIBRARY = {
    'merchandising': [
        'Bottom up item level plans',
        'Assortment planning by cluster',
        'Size and pack optimisation',
        'Attribute driven clustering',
        'Open to buy reconciliation',
        'Scenario planning and versioning',
        'Plan to actual reconciliation cadence',
        'Time to first live plan',
    ],
    'inventory_replenishment': [
        'Item and store level demand forecasting',
        'New product forecasting without history',
        'Automated allocation rules',
        'Replenishment across channels',
        'Multi echelon inventory targets',
        'Vendor lead time modelling',
        'Exception based workflow',
        'Forecast accuracy measurement',
    ],
    'pricing_promotions': [
        'Regular price optimisation',
        'Promotion planning and forecasting',
        'Markdown cadence optimisation',
        'Elasticity modelling by item and location',
        'Competitive price ingestion',
        'Margin and sell through guardrails',
        'Post event measurement',
        'Price test design and readout',
    ],
    'data_intelligence': [
        'Attribute extraction and enrichment',
        'Data quality monitoring',
        'Image and content intelligence',
        'Market and assortment benchmarking',
        'Self serve reporting for merchants',
        'Model transparency and explainability',
        'Integration with existing data platform',
        'Time to value from first data load',
    ],
}

# ─── Question banks ─────────────────────────────────────────────────────────────

DISCOVERY_LIBRARY = {
    'merchandising': [
        {'theme': 'Planning process', 'questions': [
            'How many planning tools does your team open in a single week?',
            'Where does the plan break when a category shifts mid season?',
            'Who reconciles the financial plan against the assortment plan?']},
        {'theme': 'Speed and accuracy', 'questions': [
            'How long does one full assortment refresh take today?',
            'What share of your plans hold through the season without a manual reset?']},
    ],
    'inventory_replenishment': [
        {'theme': 'Forecast quality', 'questions': [
            'How do you forecast a product with no sales history?',
            'What forecast accuracy do you measure at item and store level?',
            'How often do allocation rules get overridden by hand?']},
        {'theme': 'Inventory outcomes', 'questions': [
            'Where does excess inventory build up first?',
            'What does a stockout on a top seller cost you in a week?']},
    ],
    'pricing_promotions': [
        {'theme': 'Pricing decisions', 'questions': [
            'Who sets the markdown cadence today, and on what evidence?',
            'How do you measure the margin a promotion gave back?',
            'Can you model elasticity by store, or only by chain?']},
        {'theme': 'Governance', 'questions': [
            'What guardrails stop a price change from breaking margin targets?',
            'How quickly can you react when a competitor moves price?']},
    ],
    'data_intelligence': [
        {'theme': 'Data foundation', 'questions': [
            'How complete are the product attributes feeding your models?',
            'Who owns data quality when a model result looks wrong?',
            'How much of your reporting still lands in a spreadsheet?']},
        {'theme': 'Trust', 'questions': [
            'When a model recommends an action, can the merchant see why?',
            'What would make your team trust an automated recommendation?']},
    ],
}

OBJECTION_PROMPTS = [
    {'objection': 'We already run a platform from a larger vendor.',
     'response': 'Ask what the platform actually delivers today, then show the gap you can close in one season. Name the modules they bought and the modules they use.',
     'proof': 'Add a reference where Impact Analytics ran alongside an incumbent suite.'},
    {'objection': 'Your company is smaller than theirs.',
     'response': 'Point to the team assigned to the account and the delivery record. Size matters less than the people who show up every week.',
     'proof': 'Add a 2025 or later customer result with a source link.'},
    {'objection': 'Switching costs too much.',
     'response': 'Price the cost of staying. Compare the licence spend plus the margin lost to the plan they cannot run today.',
     'proof': 'Add the payback period from a comparable deployment.'},
    {'objection': 'We need proof the AI works on our data.',
     'response': 'Offer a scoped accuracy test on their own history. Set the success metric before the test starts.',
     'proof': 'Add the accuracy benchmark from a recent proof of value.'},
]

DOS = [
    'Lead with the customer outcome, then name the product.',
    'Quote only statistics from 2025 or later, and carry the source link.',
    'Ask the discovery questions before you present a single slide.',
    'Name the competitor once, describe the gap, then move back to value.',
    'Confirm who signs and what evidence that person needs.',
]

DONTS = [
    'Do not guess at competitor pricing or roadmap.',
    'Do not claim a capability the product does not ship today.',
    'Do not attack the rival in front of a customer who chose them.',
    'Do not send this card outside Impact Analytics.',
    'Do not present a comparison row you cannot defend with evidence.',
]

HOW_TO_USE = [
    'Read the snapshot and the win theme before the call.',
    'Run discovery first. Confirm the gap in the buyer own words.',
    'Use the matrix only when the buyer asks for a direct comparison.',
    'Set one landmine per call. More than one sounds rehearsed.',
    'Log what worked in the deal notes so the next card gets sharper.',
]

NEXT_STEPS = [
    'Book a scoped proof of value on the customer own data.',
    'Agree the success metric and the readout date in writing.',
    'Bring the economic buyer into the second meeting.',
]

# ─── Competitor presets ─────────────────────────────────────────────────────────
# Category and the IA solution most likely in play. No performance claims, no
# pricing, no customer lists. Those fields stay empty for the seller to research.

COMPETITOR_PRESETS = [
    {'name': 'o9 Solutions', 'category': 'Supply chain and demand planning platform',
     'solution': 'inventory_replenishment'},
    {'name': 'Blue Yonder', 'category': 'Retail and supply chain suite',
     'solution': 'inventory_replenishment'},
    {'name': 'RELEX Solutions', 'category': 'Retail planning and replenishment platform',
     'solution': 'inventory_replenishment'},
    {'name': 'ToolsGroup', 'category': 'Demand and inventory optimisation',
     'solution': 'inventory_replenishment'},
    {'name': 'Kinaxis', 'category': 'Supply chain orchestration platform',
     'solution': 'inventory_replenishment'},
    {'name': 'Oracle Retail', 'category': 'Enterprise retail suite',
     'solution': 'merchandising'},
    {'name': 'SAP', 'category': 'Enterprise resource and planning suite',
     'solution': 'merchandising'},
    {'name': 'Anaplan', 'category': 'Connected planning platform',
     'solution': 'merchandising'},
    {'name': 'Nextail', 'category': 'Retail merchandising and allocation',
     'solution': 'merchandising'},
    {'name': 'Increff', 'category': 'Merchandising and inventory software',
     'solution': 'merchandising'},
    {'name': 'Revionics', 'category': 'Price and promotion optimisation',
     'solution': 'pricing_promotions'},
    {'name': 'DemandTec', 'category': 'Price and promotion optimisation',
     'solution': 'pricing_promotions'},
    {'name': 'Eversight', 'category': 'Promotion and price experimentation',
     'solution': 'pricing_promotions'},
    {'name': 'SAS', 'category': 'Analytics and forecasting platform',
     'solution': 'data_intelligence'},
    {'name': 'EDITED', 'category': 'Retail market intelligence',
     'solution': 'data_intelligence'},
    {'name': 'First Insight', 'category': 'Consumer testing and product decisions',
     'solution': 'data_intelligence'},
    {'name': 'Zebra Technologies', 'category': 'Retail analytics and store operations',
     'solution': 'data_intelligence'},
]


def preset_for(name: str):
    if not name:
        return None
    for preset in COMPETITOR_PRESETS:
        if preset['name'].lower() == name.strip().lower():
            return preset
    return None


def scaffold(competitor: str = '', ia_product: str = '', solution: str = '') -> dict:
    """Build a ready to edit battlecard payload.

    Competitor facing fields carry a research prompt rather than a claim. IA
    facing fields carry portfolio language the marketing team already uses.
    """
    preset = preset_for(competitor)
    if not solution:
        solution = (PRODUCT_SOLUTIONS.get(ia_product)
                    or (preset or {}).get('solution')
                    or 'data_intelligence')
    competitor = competitor or 'Competitor name'
    product_line = ia_product or _lead_product(solution)
    solution_label = SOLUTION_LABELS.get(solution, SOLUTION_LABELS['data_intelligence'])

    return {
        'meta': {
            'competitor': competitor,
            'competitor_category': (preset or {}).get('category', ''),
            'ia_product': product_line,
            'solution': solution,
            'owner': '',
            'audience': 'Sales and solution consulting',
            'headline': 'Win %s deals against %s.' % (solution_label.lower(), competitor),
            'win_theme': 'Research the single reason this buyer switches, then lead every meeting with it.',
        },
        'how_to_use': list(HOW_TO_USE),
        'snapshot': {
            'headquarters': '', 'founded': '', 'employees': '', 'ownership': '',
            'funding': '', 'target_segment': '', 'go_to_market': '', 'deployment': '',
            'notable_customers': '',
            'recent_moves': ['Add funding, product or leadership news from the last 12 months, with a source link.'],
        },
        'positioning': {
            'their_claim': 'Paste the positioning line from their own site or latest release.',
            'our_claim': '%s runs on %s, so merchants act on one forecast instead of five spreadsheets.' % (
                solution_label, product_line),
            'wedge': 'Name the gap this buyer feels every week.',
        },
        'their_strengths': [
            'List what they genuinely do well. Credibility comes from an honest read.'],
        'their_weaknesses': [
            'List gaps you can prove with a customer story or a public source.'],
        'our_advantages': [
            {'title': 'Speed to value', 'detail': 'Describe the first outcome the customer sees, and when.',
             'proof': 'Add a customer result from 2025 or later.'},
            {'title': 'Depth of the model', 'detail': 'Describe the granularity the buyer cannot reach today.',
             'proof': 'Add the accuracy or margin metric that proves it.'},
            {'title': 'Delivery team', 'detail': 'Describe who works the account and how often.',
             'proof': 'Add a reference contact.'},
        ],
        'comparison': [
            {'capability': capability, 'ia': 'unknown', 'competitor': 'unknown', 'note': ''}
            for capability in CAPABILITY_LIBRARY.get(solution, [])
        ],
        'objections': [dict(row) for row in OBJECTION_PROMPTS],
        'landmines': [
            {'question': 'How long does one full replan take from data load to approved plan?',
             'why': 'Slow cycles expose batch architectures.',
             'listen_for': 'Any answer measured in weeks.'},
            {'question': 'Can the model explain why it recommended that action?',
             'why': 'Merchants abandon tools they cannot question.',
             'listen_for': 'A vague answer about the algorithm.'},
            {'question': 'What happens to the forecast for a product with no sales history?',
             'why': 'New product forecasting separates real models from averages.',
             'listen_for': 'A manual override process.'},
        ],
        'discovery': [dict(row) for row in DISCOVERY_LIBRARY.get(solution, [])],
        'proof_points': [
            {'stat': '', 'label': 'Add the headline result', 'detail': 'One sentence on the customer and the outcome.',
             'source': ''},
            {'stat': '', 'label': 'Add the second result', 'detail': 'Keep it to one measurable outcome.',
             'source': ''},
        ],
        'talk_track': {
            'positioning': 'For retailers who %s, Impact Analytics delivers %s through %s.' % (
                'need decisions faster than their planning cycle allows', solution_label.lower(), product_line),
            'elevator': 'Write the 30 second version. Outcome first, product second, proof third.',
            'discovery_open': 'Open with the question that exposes the gap, not with a demo.',
            'trap': 'Plant one question the incumbent answers badly.',
        },
        'dos': list(DOS),
        'donts': list(DONTS),
        'pricing': {
            'ia_model': 'Describe the Impact Analytics commercial model for this deal.',
            'competitor_model': 'Record only what the buyer tells you or what the vendor publishes.',
            'notes': ['Never quote a rival price you cannot source.'],
        },
        'next_steps': list(NEXT_STEPS),
        'resources': [
            {'label': 'Impact Analytics', 'url': 'https://www.impactanalytics.co'},
        ],
        'options': {'serif_headings': False, 'include_notes': True, 'sanitize_copy': True},
    }


def _lead_product(solution: str) -> str:
    for entry in PRODUCT_CATALOG:
        if entry['solution'] == solution:
            return entry['name']
    return 'ItemSmart'

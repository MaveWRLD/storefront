"""Frozen — imported by migration 0007. Do not change behaviour; add a new
module instead.

Pure functions only. Migration 0007 runs against historical models obtained
from `apps.get_model(...)`, which carry no custom methods or properties, so
nothing here may import from `catalog.models` or touch anything but plain
field values.

Existing rows carry no vocabulary reference, so the backfill has to infer
one. It does that from the *set of (name, code) pairs* on an axis, not from
the axis's name and not from either column alone:

    {('S','S'), ('M','M'), ('L','L'), ('XL','XL')}   -> size_letter
    {('30','W30'), ('32','W32'), ...}                -> size_waist_in
    {('Olive','OLV'), ('Rust','RST'), ...}           -> colour

Matching on the pair is what dissolves the 'Olive' vs 'OLV' ambiguity:
neither column is ever used as a standalone natural key, and the vocabulary
is decided once at the axis rather than per value. It also survives the
Color/Colour spelling split and axes named 'Waist', which an axis-name
heuristic would have to special-case.
"""

# The three vocabularies the catalog uses today, seeded by migration 0006.
# `label` is authored per entry, never derived — see the table in
# VocabularyValue's docstring for why no derivation rule could produce all
# three of these.
SEED_VOCABULARIES = [
    {
        'key': 'size_letter',
        'label': 'Letter size',
        'description': 'Alpha sizing for tops and outerwear.',
        # (value, code, label)
        'values': [
            ('S', 'S', 'S'),
            ('M', 'M', 'M'),
            ('L', 'L', 'L'),
            ('XL', 'XL', 'XL'),
        ],
    },
    {
        'key': 'size_waist_in',
        'label': 'Waist size (inches)',
        'description': 'Waist sizing for trousers and shorts.',
        'values': [
            ('30', 'W30', 'W30'),
            ('32', 'W32', 'W32'),
            ('34', 'W34', 'W34'),
            ('36', 'W36', 'W36'),
        ],
    },
    {
        'key': 'colour',
        'label': 'Colour',
        'description': 'Colourway names shared across the catalog.',
        'values': [
            ('Olive', 'OLV', 'Olive'),
            ('Rust', 'RST', 'Rust'),
            ('Sand', 'SND', 'Sand'),
            ('Sea Green', 'SEA', 'Sea Green'),
            ('Black', 'BLK', 'Black'),
            ('Slate', 'SLT', 'Slate'),
            ('Indigo', 'IND', 'Indigo'),
            ('Bone', 'BON', 'Bone'),
            ('Clay', 'CLY', 'Clay'),
            ('Navy', 'NVY', 'Navy'),
        ],
    },
]


def choose_vocabulary(axis_signature, vocab_signatures):
    """Return the vocabulary key whose value set covers `axis_signature`.

    `axis_signature` is a set of (name, code) pairs taken from one axis's
    AxisValue rows. `vocab_signatures` maps vocabulary key -> set of
    (value, code) pairs.

    Returns None when nothing matches, when the axis has no values, or when
    two or more vocabularies would qualify. Returning None on ambiguity
    rather than picking one is deliberate: a wrong guess writes a wrong
    label into the storefront, whereas None routes the row to the caller's
    failure path where a human sees it.
    """
    if not axis_signature:
        return None

    matches = [
        key for key, signature in vocab_signatures.items()
        if axis_signature <= signature
    ]
    if len(matches) != 1:
        return None
    return matches[0]


def build_vocab_signatures(vocabulary_values):
    """Group an iterable of VocabularyValue rows into {key: {(value, code)}}."""
    signatures = {}
    for vv in vocabulary_values:
        signatures.setdefault(vv.vocabulary.key, set()).add((vv.value, vv.code))
    return signatures


def build_vocab_code_signatures(vocabulary_values):
    """Group an iterable of VocabularyValue rows into {key: {code}}.

    Feeds the fallback pass described in `codes_are_usable`.
    """
    signatures = {}
    for vv in vocabulary_values:
        if vv.code:
            signatures.setdefault(vv.vocabulary.key, set()).add(vv.code)
    return signatures


def codes_are_usable(axis_values):
    """True when an axis's codes alone can identify its values.

    The same size has been spelled two ways across the catalog's history —
    `name='S'` (matching its code) and `name='Small'` (the long word) — so a
    (name, code) signature misses the long-word rows even though their codes
    are identical. Codes are the stable half of the pair, so when the pair
    pass finds nothing the backfill retries on codes alone and rewrites
    `name` to the registry's canonical `value`.

    Only safe when every code on the axis is present and distinct; a blank
    or repeated code cannot identify anything.
    """
    codes = [v.code for v in axis_values]
    return all(codes) and len(set(codes)) == len(codes)

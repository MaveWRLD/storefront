"""Unit tests for the frozen backfill matcher.

Migration 0006 imports these functions, so they are the only part of the
data migration that can be exercised directly — there is no
django-test-migrations in the Pipfile, and a RunPython body cannot be called
without a historical app registry. Testing the extracted logic is the
available option; the migration itself is verified end-to-end by
`manage.py audit_axis_labels` after it runs.
"""
import pytest

from catalog.migration_support.vocab_backfill import (
    SEED_VOCABULARIES, build_vocab_code_signatures, build_vocab_signatures,
    choose_vocabulary, codes_are_usable,
)

SIGNATURES = {
    spec['key']: {(value, code) for value, code, _ in spec['values']}
    for spec in SEED_VOCABULARIES
}
CODE_SIGNATURES = {
    spec['key']: {code for _, code, _ in spec['values'] if code}
    for spec in SEED_VOCABULARIES
}


class FakeValue:
    def __init__(self, name, code):
        self.name, self.code = name, code


class TestChooseVocabulary:
    def test_letter_sizes(self):
        signature = {('S', 'S'), ('M', 'M'), ('L', 'L'), ('XL', 'XL')}
        assert choose_vocabulary(signature, SIGNATURES) == 'size_letter'

    def test_waist_sizes_are_not_mistaken_for_letter_sizes(self):
        signature = {('30', 'W30'), ('32', 'W32')}
        assert choose_vocabulary(signature, SIGNATURES) == 'size_waist_in'

    def test_colours_resolve_on_the_pair_not_either_column(self):
        """The disambiguation the whole matcher exists for: 'Olive' alone
        and 'OLV' alone are each just one half of the key."""
        assert choose_vocabulary({('Olive', 'OLV')}, SIGNATURES) == 'colour'

    def test_a_partial_subset_still_resolves(self):
        assert choose_vocabulary({('Rust', 'RST')}, SIGNATURES) == 'colour'

    def test_unknown_values_resolve_to_nothing(self):
        assert choose_vocabulary({('Cotton', 'COT')}, SIGNATURES) is None

    def test_a_mismatched_pair_resolves_to_nothing(self):
        # Right value, wrong code — not a colour entry.
        assert choose_vocabulary({('Olive', 'OLIVE')}, SIGNATURES) is None

    def test_an_empty_axis_resolves_to_nothing(self):
        assert choose_vocabulary(set(), SIGNATURES) is None

    def test_ambiguity_returns_none_rather_than_guessing(self):
        """A wrong guess writes a wrong label into the storefront; None
        routes the row to the migration's failure path where a human sees
        it."""
        signatures = {'a': {('X', 'X')}, 'b': {('X', 'X'), ('Y', 'Y')}}
        assert choose_vocabulary({('X', 'X')}, signatures) is None


class TestCodeFallback:
    def test_long_word_names_resolve_on_code_alone(self):
        """Older rows spell the same size 'Small' where newer ones spell it
        'S'; the pair pass misses them, the code pass does not."""
        signature = {('Small', 'S'), ('Medium', 'M'), ('Large', 'L')}
        assert choose_vocabulary(signature, SIGNATURES) is None
        assert choose_vocabulary({'S', 'M', 'L'}, CODE_SIGNATURES) == 'size_letter'

    def test_codes_are_usable_when_present_and_distinct(self):
        assert codes_are_usable([FakeValue('Small', 'S'), FakeValue('Large', 'L')])

    def test_a_blank_code_makes_the_fallback_unusable(self):
        assert not codes_are_usable([FakeValue('Small', 'S'), FakeValue('Large', '')])

    def test_a_repeated_code_makes_the_fallback_unusable(self):
        assert not codes_are_usable([FakeValue('Small', 'S'), FakeValue('Petite', 'S')])


class TestSignatureBuilders:
    def test_build_vocab_signatures_groups_by_key(self):
        class FakeVocabulary:
            def __init__(self, key):
                self.key = key

        class FakeVocabularyValue:
            def __init__(self, key, value, code):
                self.vocabulary = FakeVocabulary(key)
                self.value, self.code = value, code

        rows = [FakeVocabularyValue('colour', 'Olive', 'OLV'),
                FakeVocabularyValue('colour', 'Rust', 'RST'),
                FakeVocabularyValue('size_letter', 'S', 'S')]

        assert build_vocab_signatures(rows) == {
            'colour': {('Olive', 'OLV'), ('Rust', 'RST')},
            'size_letter': {('S', 'S')},
        }
        assert build_vocab_code_signatures(rows) == {
            'colour': {'OLV', 'RST'}, 'size_letter': {'S'}}

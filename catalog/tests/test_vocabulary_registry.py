import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from catalog.migration_support.vocab_backfill import SEED_VOCABULARIES
from catalog.models import (
    AxisValue, ProductAxis, Variant, Vocabulary, VocabularyValue,
)


@pytest.mark.django_db
class TestSeededVocabularies:
    """Migration 0005 seeds these, and pytest-django builds the test DB by
    running migrations — so their presence is part of the contract, not
    something a fixture arranges."""

    @pytest.mark.parametrize('spec', SEED_VOCABULARIES,
                             ids=[s['key'] for s in SEED_VOCABULARIES])
    def test_seed_migration_created_the_vocabulary(self, spec):
        vocabulary = Vocabulary.objects.get(key=spec['key'])
        got = set(vocabulary.values.values_list('value', 'code', 'label'))
        assert got == {tuple(entry) for entry in spec['values']}

    def test_waist_labels_come_from_the_code_not_the_value(self):
        thirty = VocabularyValue.objects.get(
            vocabulary__key='size_waist_in', value='30')
        assert thirty.label == 'W30'
        assert thirty.label != thirty.value

    def test_colour_labels_come_from_the_value_not_the_code(self):
        olive = VocabularyValue.objects.get(
            vocabulary__key='colour', value='Olive')
        assert olive.label == 'Olive'
        assert olive.label != olive.code

    def test_letter_sizes_coincide(self):
        small = VocabularyValue.objects.get(
            vocabulary__key='size_letter', value='S')
        assert small.value == small.code == small.label == 'S'


@pytest.mark.django_db
class TestVocabularyValueConstraints:
    def test_value_is_unique_within_a_vocabulary(self, colour_vocab):
        with pytest.raises(IntegrityError):
            VocabularyValue.objects.create(
                vocabulary=colour_vocab, value='Olive', code='XXX',
                label='Olive again')

    def test_code_is_unique_within_a_vocabulary(self, colour_vocab):
        with pytest.raises(IntegrityError):
            VocabularyValue.objects.create(
                vocabulary=colour_vocab, value='Olivine', code='OLV',
                label='Olivine')

    def test_blank_codes_do_not_collide(self, colour_vocab):
        VocabularyValue.objects.create(
            vocabulary=colour_vocab, value='Ecru', code='', label='Ecru')
        VocabularyValue.objects.create(
            vocabulary=colour_vocab, value='Taupe', code='', label='Taupe')
        assert colour_vocab.values.filter(code='').count() == 2

    def test_label_may_not_be_blank(self, colour_vocab):
        with pytest.raises(IntegrityError):
            VocabularyValue.objects.create(
                vocabulary=colour_vocab, value='Nameless', code='NML', label='')

    def test_the_same_value_may_exist_in_two_vocabularies(
            self, colour_vocab, size_letter_vocab):
        # 'S' is a size; a colour called 'S' is unrelated. Uniqueness is
        # per vocabulary, not global.
        VocabularyValue.objects.create(
            vocabulary=colour_vocab, value='S', code='SSS', label='Sable')
        assert VocabularyValue.objects.filter(value='S').count() == 2


@pytest.mark.django_db
class TestRegistryIsProtected:
    def test_cannot_delete_a_value_in_use(self, small):
        with pytest.raises(ProtectedError):
            small.vocabulary_value.delete()

    def test_cannot_delete_a_vocabulary_an_axis_draws_from(
            self, size_axis, size_letter_vocab):
        with pytest.raises(ProtectedError):
            size_letter_vocab.delete()

    def test_unused_vocabulary_can_be_deleted_with_its_values(self):
        vocabulary = Vocabulary.objects.create(key='size_eu_shoe', label='EU shoe')
        VocabularyValue.objects.create(
            vocabulary=vocabulary, value='42', code='EU42', label='EU 42')
        vocabulary.delete()
        assert not VocabularyValue.objects.filter(value='42').exists()


@pytest.mark.django_db
class TestAxisConstraints:
    def test_a_product_may_not_draw_two_axes_from_one_vocabulary(
            self, product, size_axis, size_letter_vocab):
        """The structural half of 'no mixed vocabulary within a product' —
        a Size axis and a Waist axis both on letter sizes is the reachable
        failure, and the DB refuses it."""
        with pytest.raises(IntegrityError):
            ProductAxis.objects.create(
                product=product, name='Second size', sort_order=2,
                vocabulary=size_letter_vocab)

    def test_the_same_registry_entry_cannot_repeat_on_one_axis(
            self, size_axis, small, make_axis_value):
        with pytest.raises(IntegrityError):
            make_axis_value(size_axis, 'S')

    def test_axis_value_label_may_not_be_blank(self, size_axis, size_letter_vocab):
        vocabulary_value = VocabularyValue.objects.get(
            vocabulary=size_letter_vocab, value='M')
        with pytest.raises(IntegrityError):
            AxisValue.objects.create(
                axis=size_axis, vocabulary_value=vocabulary_value,
                name='M', code='M', label='')

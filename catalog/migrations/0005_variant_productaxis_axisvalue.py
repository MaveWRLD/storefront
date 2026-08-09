import django.core.validators
import django.db.models.deletion
import djmoney.models.fields
import djmoney.models.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0004_review_customer_review_rating_remove_review_name'),
    ]

    operations = [
        migrations.CreateModel(
            name='Variant',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sku', models.CharField(max_length=64, unique=True)),
                ('unit_price_currency', djmoney.models.fields.CurrencyField(choices=[('USD', 'US Dollar')], default='USD', editable=False, max_length=3)),
                ('unit_price', djmoney.models.fields.MoneyField(decimal_places=2, max_digits=6, validators=[djmoney.models.validators.MinMoneyValidator(1)])),
                ('compare_at_price_currency', djmoney.models.fields.CurrencyField(choices=[('USD', 'US Dollar')], default='USD', editable=False, max_length=3)),
                ('compare_at_price', djmoney.models.fields.MoneyField(blank=True, decimal_places=2, max_digits=6, null=True)),
                ('weight', models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True)),
                ('track_inventory', models.BooleanField(default=True)),
                ('inventory', models.IntegerField(default=0, validators=[django.core.validators.MinValueValidator(0)])),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='variants', to='catalog.product')),
            ],
            options={'ordering': ['id']},
        ),
        migrations.CreateModel(
            name='ProductAxis',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='axes', to='catalog.product')),
            ],
            options={'ordering': ['sort_order', 'id']},
        ),
        migrations.CreateModel(
            name='AxisValue',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('code', models.CharField(blank=True, default='', max_length=50)),
                ('axis', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='values', to='catalog.productaxis')),
            ],
            options={'ordering': ['id']},
        ),
        migrations.RemoveField(
            model_name='product',
            name='unit_price',
        ),
        migrations.RemoveField(
            model_name='product',
            name='unit_price_currency',
        ),
        migrations.RemoveField(
            model_name='product',
            name='inventory',
        ),
    ]

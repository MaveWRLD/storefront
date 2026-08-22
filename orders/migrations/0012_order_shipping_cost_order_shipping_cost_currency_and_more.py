import djmoney.models.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0011_order_subtotal_order_subtotal_currency'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='shipping_cost',
            field=djmoney.models.fields.MoneyField(decimal_places=2, default=0, default_currency='USD', max_digits=10),
        ),
        migrations.AddField(
            model_name='order',
            name='shipping_cost_currency',
            field=djmoney.models.fields.CurrencyField(default='USD', editable=False, max_length=3),
        ),
        migrations.AddField(
            model_name='order',
            name='shipping_option_token',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
    ]

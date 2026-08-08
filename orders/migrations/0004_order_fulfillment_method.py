from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0003_order_guest_email_order_guest_name_order_guest_phone_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='fulfillment_method',
            field=models.CharField(
                choices=[('PICKUP', 'Pickup'), ('DELIVERY', 'Delivery')],
                default='DELIVERY',
                max_length=8,
            ),
            preserve_default=False,
        ),
    ]

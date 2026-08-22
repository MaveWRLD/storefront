from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0013_productimage_variant'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='productimage',
            name='image',
        ),
        migrations.AddField(
            model_name='productimage',
            name='image_key',
            field=models.CharField(default='', max_length=512),
            preserve_default=False,
        ),
    ]

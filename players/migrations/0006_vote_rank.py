from django.db import migrations, models


def clear_votes(apps, schema_editor):
    """As notas de 1 a 10 não são convertíveis em posições 1..N."""
    apps.get_model('players', 'Vote').objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('players', '0005_gameconfig_hide_racha_value_and_more'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='vote',
            unique_together=set(),
        ),
        migrations.RunPython(clear_votes, migrations.RunPython.noop),
        migrations.RenameField(
            model_name='vote',
            old_name='score',
            new_name='rank',
        ),
        migrations.AlterField(
            model_name='vote',
            name='rank',
            field=models.PositiveSmallIntegerField(),
        ),
        migrations.AlterUniqueTogether(
            name='vote',
            unique_together={('player', 'voter'), ('voter', 'rank')},
        ),
    ]

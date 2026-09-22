import datetime

from django.db import migrations, models

WEEKDAY_INDEX = {'seg': 0, 'ter': 1, 'qua': 2, 'qui': 3, 'sex': 4, 'sab': 5, 'dom': 6}


def set_round_date(apps, schema_editor):
    """Os votos existentes são da rodada em andamento, ou da última encerrada."""
    Vote = apps.get_model('players', 'Vote')
    GameConfig = apps.get_model('players', 'GameConfig')

    config = GameConfig.objects.first()
    vote_day = config.vote_day if config else 'ter'
    start_time = config.vote_start_time if config else datetime.time(20, 0)

    now = datetime.datetime.now()
    days_since = (now.weekday() - WEEKDAY_INDEX[vote_day]) % 7
    round_date = now.date() - datetime.timedelta(days=days_since)

    if days_since == 0 and now.time() < start_time:
        round_date -= datetime.timedelta(days=7)

    Vote.objects.filter(round_date=None).update(round_date=round_date)


class Migration(migrations.Migration):

    dependencies = [
        ('players', '0008_remove_gameconfig_hide_racha_value_and_more'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='vote',
            unique_together=set(),
        ),
        migrations.AddField(
            model_name='vote',
            name='round_date',
            field=models.DateField(null=True),
        ),
        migrations.RunPython(set_round_date, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='vote',
            name='round_date',
            field=models.DateField(),
        ),
        migrations.AlterUniqueTogether(
            name='vote',
            unique_together={('player', 'voter', 'round_date'), ('voter', 'round_date', 'rank')},
        ),
    ]

import django.db.models.deletion
from django.db import migrations, models


def link_users(apps, schema_editor):
    """Liga cada jogador ao usuário de mesmo nome; sem usuário, o jogador sai."""
    Player = apps.get_model('players', 'Player')
    User = apps.get_model('auth', 'User')
    usuarios = {user.username: user.id for user in User.objects.all()}

    for player in Player.objects.all():
        user_id = usuarios.get(player.name)

        if user_id is None:
            player.delete()
            continue

        player.user_id = user_id
        player.save(update_fields=['user_id'])


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        ('players', '0009_vote_round_date'),
    ]

    operations = [
        migrations.AddField(
            model_name='player',
            name='user',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='player',
                to='auth.user',
            ),
        ),
        migrations.RunPython(link_users, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='player',
            name='user',
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='player',
                to='auth.user',
            ),
        ),
        migrations.RemoveField(
            model_name='player',
            name='name',
        ),
    ]

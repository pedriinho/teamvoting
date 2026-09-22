import datetime

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models


class Profile(models.Model):
    user = models.OneToOneField(User, related_name='profile', on_delete=models.CASCADE)
    avatar = models.ImageField(upload_to='avatars/', blank=True)

    def __str__(self):
        return f'Perfil de {self.user.username}'


class Player(models.Model):
    user = models.OneToOneField(User, related_name='player', on_delete=models.CASCADE)

    @property
    def name(self):
        return self.user.username

    @property
    def avatar(self):
        profile = getattr(self.user, 'profile', None)

        return profile.avatar if profile and profile.avatar else None

    @property
    def initials(self):
        return self.name[:2].upper()

    def __str__(self):
        return self.name



class Vote(models.Model):
    player = models.ForeignKey(Player, related_name='votes', on_delete=models.CASCADE)
    voter = models.ForeignKey(
        User, related_name='votes', on_delete=models.CASCADE, null=True, blank=True
    )
    round_date = models.DateField()  # dia da janela de votação em que foi dado
    rank = models.PositiveSmallIntegerField()  # 1 = mais forte

    class Meta:
        unique_together = [
            ('player', 'voter', 'round_date'),
            ('voter', 'round_date', 'rank'),
        ]

    def __str__(self):
        return f'{self.voter.username} colocou {self.player.name} na posição {self.rank}'


class VotingRound(models.Model):
    closed_on = models.DateField(unique=True)
    total_players = models.PositiveIntegerField()

    class Meta:
        ordering = ['-closed_on']

    def __str__(self):
        return f'Votação de {self.closed_on}'


class RoundResult(models.Model):
    voting_round = models.ForeignKey(VotingRound, related_name='results', on_delete=models.CASCADE)
    player_name = models.CharField(max_length=100)
    position = models.PositiveIntegerField()
    average_rank = models.FloatField(null=True, blank=True)

    class Meta:
        unique_together = ('voting_round', 'player_name')
        ordering = ['position', 'player_name']

    def __str__(self):
        return f'{self.player_name}: {self.position}º de {self.voting_round.total_players}'


class GameConfig(models.Model):
    # Dias da semana no padrão usado pela votação (compatível com datetime.weekday(),
    # onde segunda-feira = 0 ... domingo = 6).
    MONDAY = 'seg'
    TUESDAY = 'ter'
    WEDNESDAY = 'qua'
    THURSDAY = 'qui'
    FRIDAY = 'sex'
    SATURDAY = 'sab'
    SUNDAY = 'dom'

    VOTE_DAY_CHOICES = [
        (SUNDAY, 'Domingo'),
        (MONDAY, 'Segunda-feira'),
        (TUESDAY, 'Terça-feira'),
        (WEDNESDAY, 'Quarta-feira'),
        (THURSDAY, 'Quinta-feira'),
        (FRIDAY, 'Sexta-feira'),
        (SATURDAY, 'Sábado'),
    ]

    WEEKDAY_INDEX = {
        MONDAY: 0,
        TUESDAY: 1,
        WEDNESDAY: 2,
        THURSDAY: 3,
        FRIDAY: 4,
        SATURDAY: 5,
        SUNDAY: 6,
    }

    # Quantidade de jogadores por time (substitui o valor fixo que existia em views.teams)
    players_per_team = models.PositiveIntegerField(default=5)

    # Janela semanal de votação (dia + horário de início/fim)
    vote_day = models.CharField(max_length=3, choices=VOTE_DAY_CHOICES, default=TUESDAY)
    vote_start_time = models.TimeField(default=datetime.time(20, 0))
    vote_end_time = models.TimeField(default=datetime.time(23, 59))

    def clean(self):
        errors = {}

        if self.players_per_team is not None and self.players_per_team <= 0:
            errors['players_per_team'] = 'A quantidade de jogadores por time precisa ser maior que zero.'

        if self.vote_start_time and self.vote_end_time and self.vote_end_time <= self.vote_start_time:
            errors['vote_end_time'] = 'O horário final precisa ser depois do horário inicial.'

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.pk = 1
        self.full_clean()
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        config, _ = cls.objects.get_or_create(pk=1)
        return config

    def vote_weekday_index(self):
        """Retorna o índice do dia da votação no padrão de datetime.weekday()."""
        return self.WEEKDAY_INDEX[self.vote_day]
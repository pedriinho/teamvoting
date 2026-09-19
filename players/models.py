import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models


class Player(models.Model):
    name = models.CharField(max_length=100)
    is_main = models.BooleanField(default=False)  # True se estiver entre os 20 principais
    queue_position = models.PositiveIntegerField(null=True, blank=True)  # posição na lista de espera

    def average_rank(self):
        ranks = [vote.rank for vote in self.votes.all()]

        if not ranks:
            return None

        return sum(ranks) / len(ranks)

    def __str__(self):
        return self.name



class Vote(models.Model):
    player = models.ForeignKey(Player, related_name='votes', on_delete=models.CASCADE)
    voter = models.ForeignKey(
        User, related_name='votes', on_delete=models.CASCADE, null=True, blank=True
    )
    rank = models.PositiveSmallIntegerField()  # 1 = mais forte

    class Meta:
        unique_together = [('player', 'voter'), ('voter', 'rank')]

    def __str__(self):
        return f'{self.voter.username} colocou {self.player.name} na posição {self.rank}'

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

    # Quantidade máxima de jogadores na lista principal (antes limitado a 15 ou 20)
    main_players_limit = models.PositiveIntegerField(default=20)

    # Valor total do racha e se ele deve ficar oculto para usuários comuns
    racha_value = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("210.00"))
    hide_racha_value = models.BooleanField(default=False)

    # Janela semanal de votação (dia + horário de início/fim)
    vote_day = models.CharField(max_length=3, choices=VOTE_DAY_CHOICES, default=TUESDAY)
    vote_start_time = models.TimeField(default=datetime.time(20, 0))
    vote_end_time = models.TimeField(default=datetime.time(23, 59))

    def clean(self):
        errors = {}

        if self.players_per_team is not None and self.players_per_team <= 0:
            errors['players_per_team'] = 'A quantidade de jogadores por time precisa ser maior que zero.'

        if self.main_players_limit is not None and self.main_players_limit <= 0:
            errors['main_players_limit'] = 'A quantidade de jogadores na lista principal precisa ser maior que zero.'

        if self.racha_value is not None and self.racha_value <= 0:
            errors['racha_value'] = 'O valor do racha precisa ser maior que zero.'

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
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import models


class Player(models.Model):
    name = models.CharField(max_length=100)
    is_main = models.BooleanField(default=False)  # True se estiver entre os 20 principais
    queue_position = models.PositiveIntegerField(null=True, blank=True)  # posição na lista de espera

    def average_score(self):
        votes = self.votes.all()
        if votes.exists():
            return sum(vote.score for vote in votes) / votes.count()
        return 0

    def __str__(self):
        return self.name



class Vote(models.Model):
    player = models.ForeignKey(Player, related_name='votes', on_delete=models.CASCADE)
    voter = models.ForeignKey(
        User, related_name='votes', on_delete=models.CASCADE, null=True, blank=True
    )
    score = models.PositiveSmallIntegerField()

    class Meta:
        unique_together = ('player', 'voter')

    def __str__(self):
        return f'{self.voter.username} votou {self.score} para {self.player.name}'

class GameConfig(models.Model):
    main_players_limit = models.PositiveIntegerField(default=20)
    racha_value = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("210.00"))

    def save(self, *args, **kwargs):
        if self.main_players_limit not in [15, 20]:
            self.main_players_limit = 20
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        config, _ = cls.objects.get_or_create(pk=1)
        return config
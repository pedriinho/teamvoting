from django.db import models
from django.contrib.auth.models import User

class Player(models.Model):
    name = models.CharField(max_length=100)

    def average_score(self):
        votes = self.votes.all()
        if votes.exists():
            return sum(vote.score for vote in votes) / votes.count()
        return 0

    def __str__(self):
        return self.name


class Vote(models.Model):
    player = models.ForeignKey(Player, related_name='votes', on_delete=models.CASCADE)
    voter = models.ForeignKey(User, related_name='votes', on_delete=models.CASCADE, null=True, blank=True)
    score = models.PositiveSmallIntegerField()

    class Meta:
        unique_together = ('player', 'voter')

    def __str__(self):
        return f"{self.voter.username} votou {self.score} para {self.player.name}"


from django.contrib import admin

from .models import GameConfig, Player, Profile, RoundResult, Vote, VotingRound

admin.site.register(Player)
admin.site.register(Profile)
admin.site.register(Vote)
admin.site.register(GameConfig)
admin.site.register(VotingRound)
admin.site.register(RoundResult)

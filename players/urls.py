from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("add/", views.add_player, name="add_player"),
    path("vote/", views.vote, name="vote"),
    path("teams/", views.teams, name="teams"),
    path("players/", views.players, name="players"),
    path("signup/", views.signup, name="signup"),
]

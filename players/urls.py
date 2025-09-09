from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('join/', views.join_game, name='join_game'),
    path('leave/', views.leave_game, name='leave_game'),
    path('vote/', views.vote, name='vote'),
    path('teams/', views.teams, name='teams'),
    path('signup/', views.signup, name='signup'),
    path('admin-add-player/', views.admin_add_player, name='admin_add_player'),
    path('admin-remove-player/<int:player_id>/', views.admin_remove_player, name='admin_remove_player'),
]

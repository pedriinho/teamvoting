from .models import GameConfig, Player


def game_config(request):
    return {'game_config': GameConfig.load()}


def player_status(request):
    is_player = (
        request.user.is_authenticated
        and Player.objects.filter(name=request.user.username).exists()
    )
    return {'is_player': is_player}

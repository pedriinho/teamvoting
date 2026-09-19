import datetime

import pytz

from .models import GameConfig, Player

TIMEZONE = pytz.timezone("America/Sao_Paulo")


def now_local():
    return datetime.datetime.now(TIMEZONE)


def is_voting_open(config=None):
    """
    A votação fica aberta somente durante a janela configurada
    (dia da semana + horário de início/fim) em GameConfig.
    """
    config = config or GameConfig.load()
    now = now_local()

    if now.weekday() != config.vote_weekday_index():
        return False

    return config.vote_start_time <= now.time() < config.vote_end_time


def are_teams_available(config=None):
    """
    Os times ficam indisponíveis enquanto a votação estiver aberta e são
    liberados automaticamente assim que a janela de votação se encerra.
    """
    return not is_voting_open(config)


def rank_main_players(players=None):
    """
    Classifica os jogadores principais do mais forte para o mais fraco,
    anexando avg_rank (média das posições recebidas) e position (1 = mais
    forte, com empates compartilhando a posição) a cada um.
    """
    if players is None:
        players = Player.objects.filter(is_main=True)

    players = list(players)

    for player in players:
        player.avg_rank = player.average_rank()

    players.sort(
        key=lambda p: (p.avg_rank is None, p.avg_rank if p.avg_rank is not None else 0, p.name)
    )

    last_avg = object()
    position = 0

    for index, player in enumerate(players, start=1):
        if player.avg_rank != last_avg:
            position = index
            last_avg = player.avg_rank

        player.position = position

    return players

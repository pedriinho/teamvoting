import datetime
from collections import defaultdict

import pytz
from django.db import transaction

from .models import GameConfig, Player, RoundResult, Vote, VotingRound

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


def current_round_date(config=None):
    """Data da rodada em andamento, ou da última encerrada."""
    config = config or GameConfig.load()

    if is_voting_open(config):
        return now_local().date()

    return last_closed_round_date(config)


def normalized_ranks(round_date):
    """
    Média das posições de cada jogador na rodada, comparável entre listas de
    tamanhos diferentes.

    Uma posição é primeiro convertida em fração da lista em que foi dada
    ((posição - 1) / (tamanho - 1)), e a média é reescalada para a maior lista
    da rodada. Quando todas as listas têm o mesmo tamanho, o resultado é a
    média simples das posições.
    """
    ballots = defaultdict(dict)

    for player_id, voter_id, rank in Vote.objects.filter(round_date=round_date).values_list(
        'player_id', 'voter_id', 'rank'
    ):
        ballots[voter_id][player_id] = rank

    fractions = defaultdict(list)

    for ranks in ballots.values():
        size = len(ranks)

        for player_id, rank in ranks.items():
            if size > 1:
                fractions[player_id].append((rank - 1) / (size - 1))
            else:
                fractions[player_id].append(0.5)

    scale = max((len(ranks) for ranks in ballots.values()), default=0)

    return {
        player_id: sum(values) / len(values) * (scale - 1) + 1
        for player_id, values in fractions.items()
    }


def rank_players(players=None, round_date=None):
    """
    Classifica os jogadores da rodada do mais forte para o mais fraco,
    anexando avg_rank (média das posições recebidas) e position (1 = mais
    forte, com empates compartilhando a posição) a cada um.
    """
    if players is None:
        players = Player.objects.all()

    if round_date is None:
        round_date = current_round_date()

    players = list(players)
    averages = normalized_ranks(round_date)

    for player in players:
        player.avg_rank = averages.get(player.id)

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


def last_closed_round_date(config=None):
    """Data da última janela de votação que já se encerrou."""
    config = config or GameConfig.load()
    now = now_local()
    days_since_vote_day = (now.weekday() - config.vote_weekday_index()) % 7
    date = now.date() - datetime.timedelta(days=days_since_vote_day)

    if days_since_vote_day == 0 and now.time() < config.vote_end_time:
        date -= datetime.timedelta(days=7)

    return date


def archive_closed_round(config=None):
    """Arquiva a classificação da rodada encerrada, uma única vez por rodada."""
    config = config or GameConfig.load()

    if is_voting_open(config):
        return None

    closed_on = last_closed_round_date(config)

    if VotingRound.objects.filter(closed_on=closed_on).exists():
        return None

    if not Vote.objects.filter(round_date=closed_on).exists():
        return None

    ranked = rank_players(round_date=closed_on)

    if not ranked:
        return None

    with transaction.atomic():
        voting_round = VotingRound.objects.create(closed_on=closed_on, total_players=len(ranked))
        RoundResult.objects.bulk_create([
            RoundResult(
                voting_round=voting_round,
                player_name=player.name,
                position=player.position,
                average_rank=player.avg_rank,
            )
            for player in ranked
        ])

    return voting_round

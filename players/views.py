import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import redirect, render, get_object_or_404

from .decorators import only_tuesday_evening, vote_open_only
from .models import GameConfig, Player, RoundResult, Vote
from .utils import archive_closed_round, are_teams_available, current_round_date, rank_players

ERROR_TRANSLATIONS = {
    "A user with that username already exists.": "Já existe um usuário com esse nome.",
    "This password is too short. It must contain at least 8 characters.": "A senha é muito curta. Deve ter pelo menos 8 caracteres.",
    "The two password fields didn’t match.": "As senhas não coincidem.",
    "This field is required.": "Este campo é obrigatório.",
}


def compact_vote_ranks():
    """Renumera a lista de cada votante para 1..N, fechando buracos."""
    ballots = Vote.objects.exclude(voter=None).values_list('voter_id', 'round_date').distinct()

    for voter_id, round_date in ballots:
        ballot = Vote.objects.filter(voter_id=voter_id, round_date=round_date)
        votes = list(ballot.order_by('rank', 'id'))

        if [vote.rank for vote in votes] == list(range(1, len(votes) + 1)):
            continue

        with transaction.atomic():
            ballot.delete()
            Vote.objects.bulk_create([
                Vote(
                    player_id=vote.player_id,
                    voter_id=voter_id,
                    round_date=round_date,
                    rank=position,
                )
                for position, vote in enumerate(votes, start=1)
            ])


def home(request):
    config = GameConfig.load()
    archive_closed_round(config)

    show_scores = are_teams_available()

    if show_scores:
        players = rank_players(Player.objects.select_related('user'))
    else:
        players = list(Player.objects.select_related('user').order_by('id'))

    return render(request, 'players/home.html', {
        'players': players,
        'show_scores': show_scores,
        'player_count': len(players),
    })


@login_required
def join_game(request):
    if not Player.objects.filter(user=request.user).exists():
        Player.objects.create(user=request.user)

    return redirect('home')


@login_required
def leave_game(request):
    player = get_object_or_404(Player, user=request.user)

    Vote.objects.filter(player_id=player.id).delete()
    Vote.objects.filter(voter=request.user).delete()

    player.delete()
    compact_vote_ranks()

    return redirect('home')


@login_required
@vote_open_only
def vote(request):
    players = list(Player.objects.exclude(user=request.user).select_related('user'))
    player_ids = {player.id for player in players}

    round_date = current_round_date()

    if request.method == 'POST':
        raw_order = request.POST.get('order', '')

        try:
            ordered_ids = [int(chunk) for chunk in raw_order.split(',') if chunk]
        except ValueError:
            ordered_ids = []

        if sorted(ordered_ids) != sorted(player_ids):
            messages.error(
                request,
                'A ordenação enviada não corresponde à lista de jogadores. Tente novamente.',
            )
            return redirect('vote')

        with transaction.atomic():
            Vote.objects.filter(voter=request.user, round_date=round_date).delete()
            Vote.objects.bulk_create([
                Vote(
                    player_id=player_id,
                    voter=request.user,
                    round_date=round_date,
                    rank=position,
                )
                for position, player_id in enumerate(ordered_ids, start=1)
            ])

        messages.success(request, 'Sua ordenação foi registrada!')

        return redirect('home')

    existing_ranks = dict(
        Vote.objects.filter(voter=request.user, round_date=round_date)
        .values_list('player_id', 'rank')
    )

    players.sort(key=lambda p: (p.id not in existing_ranks, existing_ranks.get(p.id, 0), p.name))

    return render(request, 'players/vote.html', {
        'players': players,
        'has_saved_vote': bool(existing_ranks),
    })


@only_tuesday_evening
def teams(request):
    archive_closed_round()

    players = rank_players(Player.objects.select_related('user'))
    total_players = len(players)
    max_team_size = GameConfig.load().players_per_team
    num_teams = (total_players + max_team_size - 1) // max_team_size
    teams = [[] for _ in range(num_teams)]
    team_strengths = [0] * num_teams

    for player in players:
        player.strength = total_players + 1 - player.position

        best_index = min(
            (i for i in range(num_teams) if len(teams[i]) < max_team_size),
            key=lambda i: (len(teams[i]), team_strengths[i])
        )
        teams[best_index].append(player)
        team_strengths[best_index] += player.strength

    teams_with_summary = [
        {
            'players': team,
            'average_position': sum(p.position for p in team) / len(team) if team else 0,
        }
        for team in teams
    ]

    return render(request, 'players/teams.html', {'teams': teams_with_summary})


@login_required
def account(request):
    archive_closed_round()

    name = request.user.username
    player = Player.objects.filter(user=request.user).first()

    history = list(
        RoundResult.objects.filter(player_name=name)
        .select_related('voting_round')
        .order_by('-voting_round__closed_on')
    )

    best_position = min((result.position for result in history), default=None)

    current = None

    if player and are_teams_available():
        ranked = rank_players(Player.objects.select_related('user'))
        current = next((p for p in ranked if p.id == player.id), None)

        if current is not None:
            current.total_players = len(ranked)

    return render(request, 'players/account.html', {
        'player': player,
        'history': history,
        'best_position': best_position,
        'current': current,
        'rounds_played': len(history),
    })


def signup(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)

        if form.is_valid():
            form.save()
            return redirect('login')

        for field, errors in form.errors.items():
            field_name = {
                'username': 'Nome de usuário',
                'password1': 'Senha',
                'password2': 'Confirmação de senha',
            }.get(field, field)

            for error in errors:
                translated_error = ERROR_TRANSLATIONS.get(error, error)
                messages.error(request, f"{field_name}: {translated_error}")
    else:
        form = UserCreationForm()

    return render(request, 'players/signup.html', {'form': form})


@user_passes_test(lambda u: u.is_superuser)
def admin_add_player(request):
    users_to_add = User.objects.filter(player=None)

    if request.method == 'POST':
        username = request.POST.get('username')

        if username:
            user = get_object_or_404(User, username=username)
            Player.objects.get_or_create(user=user)
            messages.success(request, f'Usuário {username} adicionado!')

            return redirect('home')

    return render(request, 'players/admin_add_player.html', {'users_to_add': users_to_add})


@user_passes_test(lambda u: u.is_superuser)
def admin_remove_player(request, player_id):
    player = get_object_or_404(Player, id=player_id)

    Vote.objects.filter(player=player).delete()
    Vote.objects.filter(voter=player.user).delete()

    player.delete()
    compact_vote_ranks()

    return redirect('home')


@user_passes_test(lambda u: u.is_superuser)
def admin_update_settings(request):
    if request.method == 'POST':
        config = GameConfig.load()

        try:
            players_per_team = int(request.POST.get('players_per_team', ''))
        except (TypeError, ValueError):
            messages.error(request, 'Quantidade de jogadores por time inválida.')
            return redirect('/')

        vote_day = request.POST.get('vote_day')
        vote_start_time = request.POST.get('vote_start_time')
        vote_end_time = request.POST.get('vote_end_time')

        try:
            parsed_start_time = datetime.datetime.strptime(vote_start_time, '%H:%M').time()
            parsed_end_time = datetime.datetime.strptime(vote_end_time, '%H:%M').time()
        except (TypeError, ValueError):
            messages.error(request, 'Horário de início/encerramento da votação inválido.')
            return redirect('/')

        config.players_per_team = players_per_team
        config.vote_day = vote_day
        config.vote_start_time = parsed_start_time
        config.vote_end_time = parsed_end_time

        try:
            config.save()
        except ValidationError as exc:
            for field_errors in exc.message_dict.values():
                for error in field_errors:
                    messages.error(request, error)
            return redirect('/')

        messages.success(request, 'Configurações atualizadas com sucesso.')

    return redirect('/')

@user_passes_test(lambda u: u.is_superuser)
def admin_clear_players(request):
    if request.method == 'POST':
        Vote.objects.all().delete()
        Player.objects.all().delete()
        messages.success(request, 'Todos os jogadores foram removidos das listas.')

    return redirect('/')
from django.shortcuts import render, redirect
from .models import Player, Vote
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm


def home(request):
    players = Player.objects.all()
    return render(request, "players/home.html", {"players": players})


def add_player(request):
    if request.method == "POST":
        name = request.POST.get("name")
        if name:
            Player.objects.create(name=name)
            return redirect("home")
    return render(request, "players/add_player.html")


@login_required
def vote(request):
    players = Player.objects.all()
    message = ""

    if request.method == "POST":
        for player in players:
            score = request.POST.get(f"score_{player.id}")
            if score and score.isdigit():
                score_int = int(score)
                if 1 <= score_int <= 10:
                    # Cria ou atualiza o voto para o jogador e usuário atual
                    Vote.objects.update_or_create(
                        player=player, voter=request.user, defaults={"score": score_int}
                    )
        return redirect("teams")  # redireciona depois de salvar

    else:
        # Método GET: vamos carregar os votos existentes para preencher o formulário
        # Cria um dicionário com player_id -> score do voto existente (se houver)
        existing_votes = Vote.objects.filter(voter=request.user)
        votes_dict = {vote.player.id: vote.score for vote in existing_votes}

    return render(
        request,
        "players/vote.html",
        {"players": players, "votes_dict": votes_dict, "message": message},
    )


def teams(request):
    players = list(Player.objects.all())
    players = sorted(players, key=lambda p: p.average_score(), reverse=True)

    max_team_size = 5
    num_teams = (len(players) + max_team_size - 1) // max_team_size

    teams = [[] for _ in range(num_teams)]
    team_scores = [0] * num_teams

    for player in players:
        # Encontra o time com menor soma de avaliação e que ainda não está cheio
        best_index = min(
            (i for i in range(num_teams) if len(teams[i]) < max_team_size),
            key=lambda i: team_scores[i],
        )
        teams[best_index].append(player)
        team_scores[best_index] += player.average_score()

    return render(request, "players/teams.html", {"teams": teams})


def players(request):
    players = list(Player.objects.all())
    players = sorted(players, key=lambda p: p.average_score(), reverse=True)

    return render(request, "players/players.html", {"players": players})


def signup(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("login")
    else:
        form = UserCreationForm()
    return render(request, "players/signup.html", {"form": form})

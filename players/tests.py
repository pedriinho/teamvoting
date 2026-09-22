import datetime
import pathlib
import shutil
import tempfile
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from .models import GameConfig, Player, Profile, RoundResult, Vote, VotingRound
from .utils import TIMEZONE, archive_closed_round, current_round_date, rank_players
from .views import compact_vote_ranks

CREDENCIAL_DE_TESTE = 'racha-1234'


def make_players(*names):
    return [
        Player.objects.create(user=User.objects.create_user(name, password=CREDENCIAL_DE_TESTE))
        for name in names
    ]


def cast_ballot(voter, ordered_players, round_date=None):
    round_date = round_date or current_round_date()

    for position, player in enumerate(ordered_players, start=1):
        Vote.objects.create(
            player=player, voter=voter, round_date=round_date, rank=position
        )


class RankPlayersTests(TestCase):
    def test_orders_by_average_received_rank(self):
        ana, bruno, caio = make_players('ana', 'bruno', 'caio')
        voter_one = User.objects.create_user('voter_one', password=CREDENCIAL_DE_TESTE)
        voter_two = User.objects.create_user('voter_two', password=CREDENCIAL_DE_TESTE)

        cast_ballot(voter_one, [caio, ana, bruno])
        cast_ballot(voter_two, [caio, bruno, ana])

        ranked = rank_players()

        self.assertEqual([p.name for p in ranked], ['caio', 'ana', 'bruno'])
        self.assertEqual([p.position for p in ranked], [1, 2, 2])
        self.assertAlmostEqual(ranked[0].avg_rank, 1.0)
        self.assertAlmostEqual(ranked[1].avg_rank, 2.5)
        self.assertAlmostEqual(ranked[2].avg_rank, 2.5)

    def test_ties_share_the_same_position(self):
        ana, bruno, caio = make_players('ana', 'bruno', 'caio')
        voter = User.objects.create_user('voter', password=CREDENCIAL_DE_TESTE)
        other = User.objects.create_user('other', password=CREDENCIAL_DE_TESTE)

        cast_ballot(voter, [ana, bruno, caio])
        cast_ballot(other, [bruno, ana, caio])

        ranked = rank_players()

        self.assertEqual(
            [(p.name, p.position) for p in ranked],
            [('ana', 1), ('bruno', 1), ('caio', 3)],
        )

    def test_equal_sized_ballots_keep_the_plain_average(self):
        ana, bruno = make_players('ana', 'bruno')
        voter = User.objects.create_user('voter', password=CREDENCIAL_DE_TESTE)
        other = User.objects.create_user('other', password=CREDENCIAL_DE_TESTE)

        cast_ballot(voter, [ana, bruno])
        cast_ballot(other, [ana, bruno])

        ranked = rank_players()

        self.assertAlmostEqual(ranked[0].avg_rank, 1.0)
        self.assertAlmostEqual(ranked[1].avg_rank, 2.0)

    def test_ballots_of_different_sizes_are_comparable(self):
        ana, bruno, caio = make_players('ana', 'bruno', 'caio')
        curta = User.objects.create_user('curta', password=CREDENCIAL_DE_TESTE)
        longa = User.objects.create_user('longa', password=CREDENCIAL_DE_TESTE)

        cast_ballot(curta, [ana, bruno])
        cast_ballot(longa, [bruno, ana, caio])

        ranked = rank_players()

        # Na média simples ana e bruno empatariam em 1.5, embora o 2º lugar de
        # bruno numa lista de dois seja o último e o de ana numa de três não.
        self.assertEqual([p.name for p in ranked], ['ana', 'bruno', 'caio'])
        self.assertAlmostEqual(ranked[0].avg_rank, 1.5)
        self.assertAlmostEqual(ranked[1].avg_rank, 2.0)
        self.assertAlmostEqual(ranked[2].avg_rank, 3.0)

    def test_players_without_votes_go_last(self):
        ana, bruno = make_players('ana', 'bruno')
        voter = User.objects.create_user('voter', password=CREDENCIAL_DE_TESTE)

        Vote.objects.create(
            player=bruno, voter=voter, round_date=current_round_date(), rank=5
        )

        ranked = rank_players()

        self.assertEqual([p.name for p in ranked], ['bruno', 'ana'])
        self.assertIsNone(ranked[1].avg_rank)


class CompactVoteRanksTests(TestCase):
    def test_closes_the_gap_left_by_a_removed_player(self):
        ana, bruno, caio = make_players('ana', 'bruno', 'caio')
        voter = User.objects.create_user('voter', password=CREDENCIAL_DE_TESTE)

        cast_ballot(voter, [ana, bruno, caio])
        Vote.objects.filter(player=bruno).delete()
        bruno.delete()

        compact_vote_ranks()

        remaining = Vote.objects.filter(voter=voter).order_by('rank')
        self.assertEqual([(v.player.name, v.rank) for v in remaining], [('ana', 1), ('caio', 2)])


class VoteViewTests(TestCase):
    def setUp(self):
        self.voter = User.objects.create_user('ana', password=CREDENCIAL_DE_TESTE)
        self.ana = Player.objects.create(user=self.voter)
        self.bruno, self.caio = make_players('bruno', 'caio')
        self.client.force_login(self.voter)

        patcher = patch('players.decorators.is_voting_open', return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_small_lists_start_on_the_drag_list(self):
        response = self.client.get(reverse('vote'))

        self.assertFalse(response.context['start_with_duels'])

    def test_long_lists_start_on_duels(self):
        make_players(*[f'jogador{i}' for i in range(12)])

        response = self.client.get(reverse('vote'))

        self.assertTrue(response.context['start_with_duels'])

    def test_a_saved_ballot_always_opens_on_the_list(self):
        make_players(*[f'jogador{i}' for i in range(12)])
        cast_ballot(self.voter, list(Player.objects.exclude(user=self.voter)))

        response = self.client.get(reverse('vote'))

        self.assertFalse(response.context['start_with_duels'])

    def test_page_lists_the_other_main_players(self):
        response = self.client.get(reverse('vote'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual([p.name for p in response.context['players']], ['bruno', 'caio'])

    def test_saved_order_is_reloaded(self):
        cast_ballot(self.voter, [self.caio, self.bruno])

        response = self.client.get(reverse('vote'))

        self.assertEqual([p.name for p in response.context['players']], ['caio', 'bruno'])
        self.assertTrue(response.context['has_saved_vote'])

    def test_posting_an_order_stores_positions(self):
        response = self.client.post(reverse('vote'), {'order': f'{self.caio.id},{self.bruno.id}'})

        self.assertRedirects(response, reverse('home'))
        stored = Vote.objects.filter(voter=self.voter).order_by('rank')
        self.assertEqual([(v.player.name, v.rank) for v in stored], [('caio', 1), ('bruno', 2)])

    def test_posting_again_replaces_the_previous_order(self):
        self.client.post(reverse('vote'), {'order': f'{self.caio.id},{self.bruno.id}'})
        self.client.post(reverse('vote'), {'order': f'{self.bruno.id},{self.caio.id}'})

        stored = Vote.objects.filter(voter=self.voter).order_by('rank')
        self.assertEqual([(v.player.name, v.rank) for v in stored], [('bruno', 1), ('caio', 2)])

    def test_incomplete_or_duplicated_order_is_rejected(self):
        for payload in [
            {'order': f'{self.bruno.id}'},
            {'order': f'{self.bruno.id},{self.bruno.id}'},
            {'order': f'{self.bruno.id},{self.caio.id},{self.ana.id}'},
            {'order': 'abc'},
            {},
        ]:
            with self.subTest(payload=payload):
                response = self.client.post(reverse('vote'), payload)

                self.assertRedirects(response, reverse('vote'))
                self.assertFalse(Vote.objects.filter(voter=self.voter).exists())


class TeamsViewTests(TestCase):
    def setUp(self):
        patcher = patch('players.decorators.are_teams_available', return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_teams_are_balanced_by_position(self):
        config = GameConfig.load()
        config.players_per_team = 2
        config.save()

        players = make_players('p1', 'p2', 'p3', 'p4')
        voter = User.objects.create_user('voter', password=CREDENCIAL_DE_TESTE)
        cast_ballot(voter, players)

        response = self.client.get(reverse('teams'))
        teams = response.context['teams']

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(teams), 2)
        self.assertEqual([[p.name for p in team['players']] for team in teams],
                         [['p1', 'p4'], ['p2', 'p3']])
        self.assertEqual([team['average_position'] for team in teams], [2.5, 2.5])


class ArchiveClosedRoundTests(TestCase):
    def setUp(self):
        config = GameConfig.load()
        config.vote_day = GameConfig.TUESDAY
        config.save()
        self.config = config

        self.ana, self.bruno = make_players('ana', 'bruno')
        self.voter = User.objects.create_user('voter', password=CREDENCIAL_DE_TESTE)
        self.rodada = datetime.date(2026, 9, 15)
        cast_ballot(self.voter, [self.bruno, self.ana], round_date=self.rodada)

    def fake_now(self, weekday, hour):
        base = datetime.datetime(2026, 9, 15, hour, 0)  # 2026-09-15 é uma terça
        moment = base + datetime.timedelta(days=weekday - 1)
        return TIMEZONE.localize(moment)

    def test_archives_once_after_the_window_closes(self):
        fim_da_janela = self.fake_now(1, 23).replace(minute=59)

        with patch('players.utils.now_local', return_value=fim_da_janela):
            first = archive_closed_round()
            second = archive_closed_round()

        self.assertIsNotNone(first)
        self.assertIsNone(second)
        self.assertEqual(VotingRound.objects.count(), 1)
        self.assertEqual(first.closed_on, datetime.date(2026, 9, 15))
        self.assertEqual(first.total_players, 2)
        self.assertEqual(
            [(r.player_name, r.position) for r in first.results.all()],
            [('bruno', 1), ('ana', 2)],
        )

    def test_does_not_archive_while_voting_is_open(self):
        dentro_da_janela = self.fake_now(1, 20).replace(minute=30)

        with patch('players.utils.now_local', return_value=dentro_da_janela):
            self.assertIsNone(archive_closed_round())

        self.assertEqual(VotingRound.objects.count(), 0)

    def test_before_the_window_the_round_belongs_to_the_previous_week(self):
        semana_passada = datetime.date(2026, 9, 8)
        Vote.objects.all().delete()
        cast_ballot(self.voter, [self.bruno, self.ana], round_date=semana_passada)

        with patch('players.utils.now_local', return_value=self.fake_now(1, 10)):
            voting_round = archive_closed_round()

        self.assertEqual(voting_round.closed_on, semana_passada)

    def test_midweek_archives_under_the_last_vote_day(self):
        with patch('players.utils.now_local', return_value=self.fake_now(3, 12)):
            voting_round = archive_closed_round()

        self.assertEqual(voting_round.closed_on, datetime.date(2026, 9, 15))

    def test_nothing_to_archive_without_votes(self):
        Vote.objects.all().delete()

        with patch('players.utils.now_local', return_value=self.fake_now(3, 12)):
            self.assertIsNone(archive_closed_round())

    def test_history_survives_the_player_leaving(self):
        with patch('players.utils.now_local', return_value=self.fake_now(3, 12)):
            archive_closed_round()

        Vote.objects.filter(player=self.bruno).delete()
        self.bruno.delete()

        self.assertEqual(RoundResult.objects.filter(player_name='bruno').count(), 1)


class AccountViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('ana', password=CREDENCIAL_DE_TESTE)
        self.client.force_login(self.user)

    def test_requires_login(self):
        self.client.logout()

        response = self.client.get(reverse('account'))

        self.assertEqual(response.status_code, 302)

    def test_shows_position_per_closed_round(self):
        first = VotingRound.objects.create(closed_on=datetime.date(2026, 9, 8), total_players=12)
        second = VotingRound.objects.create(closed_on=datetime.date(2026, 9, 15), total_players=10)
        RoundResult.objects.create(
            voting_round=first, player_name='ana', position=7, average_rank=6.5
        )
        RoundResult.objects.create(
            voting_round=second, player_name='ana', position=3, average_rank=3.2
        )
        RoundResult.objects.create(
            voting_round=second, player_name='bruno', position=1, average_rank=1.0
        )

        response = self.client.get(reverse('account'))
        history = response.context['history']

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [(r.position, r.voting_round.total_players) for r in history],
            [(3, 10), (7, 12)],
        )
        self.assertEqual(response.context['best_position'], 3)
        self.assertEqual(response.context['rounds_played'], 2)
        self.assertContains(response, '3º de 10')

    def test_current_position_appears_when_voting_is_closed(self):
        ana = Player.objects.create(user=self.user)
        (bruno,) = make_players('bruno')
        voter = User.objects.create_user('voter', password=CREDENCIAL_DE_TESTE)
        cast_ballot(voter, [bruno, ana])

        with patch('players.views.are_teams_available', return_value=True):
            response = self.client.get(reverse('account'))

        current = response.context['current']
        self.assertEqual((current.position, current.total_players), (2, 2))

    def test_page_works_for_a_user_without_a_player(self):
        response = self.client.get(reverse('account'))

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context['player'])
        self.assertIsNone(response.context['best_position'])
        self.assertEqual(response.context['history'], [])


class JoinGameTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('ana', password=CREDENCIAL_DE_TESTE)
        self.client.force_login(self.user)

    def test_everyone_who_joins_plays(self):
        make_players(*[f'jogador{i}' for i in range(30)])

        response = self.client.post(reverse('join_game'))

        self.assertRedirects(response, reverse('home'))
        self.assertTrue(Player.objects.filter(user=self.user).exists())
        self.assertEqual(Player.objects.count(), 31)

    def test_joining_twice_does_not_duplicate(self):
        self.client.post(reverse('join_game'))
        self.client.post(reverse('join_game'))

        self.assertEqual(Player.objects.filter(user=self.user).count(), 1)

    def test_leaving_removes_the_player_and_the_votes(self):
        ana = Player.objects.create(user=self.user)
        (bruno,) = make_players('bruno')
        voter = User.objects.create_user('voter', password=CREDENCIAL_DE_TESTE)
        cast_ballot(voter, [ana, bruno])

        response = self.client.post(reverse('leave_game'))

        self.assertRedirects(response, reverse('home'))
        self.assertFalse(Player.objects.filter(user=self.user).exists())
        self.assertEqual(
            [(v.player.name, v.rank) for v in Vote.objects.all()],
            [('bruno', 1)],
        )


class HomeViewTests(TestCase):
    def test_lists_every_player_with_the_ranking_once_voting_closed(self):
        players = make_players('ana', 'bruno', 'caio')
        voter = User.objects.create_user('voter', password=CREDENCIAL_DE_TESTE)
        cast_ballot(voter, [players[2], players[0], players[1]])

        with patch('players.views.are_teams_available', return_value=True):
            response = self.client.get(reverse('home'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['player_count'], 3)
        self.assertEqual([p.name for p in response.context['players']], ['caio', 'ana', 'bruno'])

    def test_ranking_is_hidden_while_voting_is_open(self):
        make_players('ana', 'bruno')

        with patch('players.views.are_teams_available', return_value=False):
            response = self.client.get(reverse('home'))

        self.assertFalse(response.context['show_scores'])
        self.assertContains(response, 'Liberado após o encerramento da votação')


class RoundScopeTests(TestCase):
    def setUp(self):
        self.ana, self.bruno = make_players('ana', 'bruno')
        self.voter = User.objects.create_user('voter', password=CREDENCIAL_DE_TESTE)

    def test_previous_round_votes_do_not_count(self):
        antiga = current_round_date() - datetime.timedelta(days=7)
        cast_ballot(self.voter, [self.bruno, self.ana], round_date=antiga)

        ranked = rank_players()

        self.assertEqual([p.avg_rank for p in ranked], [None, None])

    def test_each_round_keeps_its_own_ballot(self):
        antiga = current_round_date() - datetime.timedelta(days=7)
        cast_ballot(self.voter, [self.bruno, self.ana], round_date=antiga)
        cast_ballot(self.voter, [self.ana, self.bruno])

        self.assertEqual(Vote.objects.count(), 4)
        self.assertEqual([p.name for p in rank_players()], ['ana', 'bruno'])
        self.assertEqual([p.name for p in rank_players(round_date=antiga)], ['bruno', 'ana'])

    def test_voting_replaces_only_the_current_round(self):
        antiga = current_round_date() - datetime.timedelta(days=7)
        cast_ballot(self.voter, [self.bruno, self.ana], round_date=antiga)

        self.client.force_login(self.voter)

        with patch('players.decorators.is_voting_open', return_value=True):
            self.client.post(reverse('vote'), {'order': f'{self.ana.id},{self.bruno.id}'})

        self.assertEqual(Vote.objects.filter(round_date=antiga).count(), 2)
        self.assertEqual([p.name for p in rank_players()], ['ana', 'bruno'])


class PlayerUserLinkTests(TestCase):
    def test_a_user_has_at_most_one_player(self):
        user = User.objects.create_user('ana', password=CREDENCIAL_DE_TESTE)
        Player.objects.create(user=user)

        with self.assertRaises(IntegrityError), transaction.atomic():
            Player.objects.create(user=user)

    def test_name_comes_from_the_user(self):
        user = User.objects.create_user('ana', password=CREDENCIAL_DE_TESTE)
        player = Player.objects.create(user=user)

        user.username = 'ana-maria'
        user.save()
        player.refresh_from_db()

        self.assertEqual(player.name, 'ana-maria')

    def test_removing_the_user_removes_the_player(self):
        user = User.objects.create_user('ana', password=CREDENCIAL_DE_TESTE)
        Player.objects.create(user=user)

        user.delete()

        self.assertEqual(Player.objects.count(), 0)


class AdminRemovePlayerTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            'chefe', 'chefe@exemplo.com', CREDENCIAL_DE_TESTE
        )
        self.client.force_login(self.admin)
        (self.ana,) = make_players('ana')

    def test_get_does_not_remove(self):
        response = self.client.get(reverse('admin_remove_player', args=[self.ana.id]))

        self.assertEqual(response.status_code, 405)
        self.assertTrue(Player.objects.filter(id=self.ana.id).exists())

    def test_post_removes(self):
        response = self.client.post(reverse('admin_remove_player', args=[self.ana.id]))

        self.assertRedirects(response, reverse('home'))
        self.assertFalse(Player.objects.filter(id=self.ana.id).exists())


def image_upload(name='foto.png', size=(600, 400), fmt='PNG'):
    buffer = BytesIO()
    Image.new('RGB', size, (10, 120, 200)).save(buffer, format=fmt)

    return SimpleUploadedFile(name, buffer.getvalue(), content_type=f'image/{fmt.lower()}')


class AvatarUploadTests(TestCase):
    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, True)

        self.user = User.objects.create_user('ana', password=CREDENCIAL_DE_TESTE)
        self.client.force_login(self.user)

        overrides = override_settings(MEDIA_ROOT=self.media)
        overrides.enable()
        self.addCleanup(overrides.disable)

    def profile(self):
        return Profile.objects.get(user=self.user)

    def test_upload_is_cropped_to_a_square(self):
        response = self.client.post(reverse('avatar_update'), {'avatar': image_upload()})

        self.assertRedirects(response, reverse('account'))

        with Image.open(self.profile().avatar.path) as saved:
            self.assertEqual(saved.size, (256, 256))
            self.assertEqual(saved.format, 'JPEG')

    def test_upload_replaces_the_previous_file(self):
        self.client.post(reverse('avatar_update'), {'avatar': image_upload()})
        primeira = self.profile().avatar.path

        self.client.post(reverse('avatar_update'), {'avatar': image_upload('outra.png')})
        segunda = self.profile().avatar.path

        # O nome é derivado do usuário, então a foto nova ocupa o mesmo arquivo
        # e não sobra nada para trás.
        self.assertEqual(primeira, segunda)
        self.assertTrue(pathlib.Path(segunda).exists())
        self.assertEqual(len(list((pathlib.Path(self.media) / 'avatars').iterdir())), 1)

    def test_a_file_that_is_not_an_image_is_rejected(self):
        naoimagem = SimpleUploadedFile('vote.txt', b'nao sou imagem', content_type='image/png')

        response = self.client.post(reverse('avatar_update'), {'avatar': naoimagem})

        self.assertRedirects(response, reverse('account'))
        self.assertFalse(self.profile().avatar)

    def test_oversized_file_is_rejected(self):
        grande = SimpleUploadedFile('grande.png', b'x' * (5 * 1024 * 1024 + 1))

        self.client.post(reverse('avatar_update'), {'avatar': grande})

        self.assertFalse(self.profile().avatar)

    def test_removing_deletes_the_file(self):
        self.client.post(reverse('avatar_update'), {'avatar': image_upload()})
        caminho = self.profile().avatar.path

        self.client.post(reverse('avatar_update'), {'remove': '1'})

        self.assertFalse(self.profile().avatar)
        self.assertFalse(pathlib.Path(caminho).exists())

    def test_get_is_not_allowed(self):
        response = self.client.get(reverse('avatar_update'))

        self.assertEqual(response.status_code, 405)

    def test_the_photo_shows_up_on_the_vote_page(self):
        Player.objects.create(user=self.user)
        (bruno,) = make_players('bruno')
        self.client.force_login(bruno.user)
        self.client.post(reverse('avatar_update'), {'avatar': image_upload()})
        url_foto = Profile.objects.get(user=bruno.user).avatar.url

        self.client.force_login(self.user)

        with patch('players.decorators.is_voting_open', return_value=True):
            response = self.client.get(reverse('vote'))

        self.assertContains(response, url_foto)

    def test_players_without_a_photo_fall_back_to_initials(self):
        Player.objects.create(user=self.user)
        make_players('bruno')

        with patch('players.decorators.is_voting_open', return_value=True):
            response = self.client.get(reverse('vote'))

        self.assertContains(response, 'data-iniciais="BR"')

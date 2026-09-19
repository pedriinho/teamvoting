from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import GameConfig, Player, Vote
from .utils import rank_main_players
from .views import compact_vote_ranks

CREDENCIAL_DE_TESTE = 'racha-1234'


def make_players(*names):
    return [Player.objects.create(name=name, is_main=True) for name in names]


def cast_ballot(voter, ordered_players):
    for position, player in enumerate(ordered_players, start=1):
        Vote.objects.create(player=player, voter=voter, rank=position)


class RankMainPlayersTests(TestCase):
    def test_orders_by_average_received_rank(self):
        ana, bruno, caio = make_players('ana', 'bruno', 'caio')
        voter_one = User.objects.create_user('voter_one', password=CREDENCIAL_DE_TESTE)
        voter_two = User.objects.create_user('voter_two', password=CREDENCIAL_DE_TESTE)

        cast_ballot(voter_one, [caio, ana, bruno])
        cast_ballot(voter_two, [caio, bruno, ana])

        ranked = rank_main_players()

        self.assertEqual([p.name for p in ranked], ['caio', 'ana', 'bruno'])
        self.assertEqual([p.position for p in ranked], [1, 2, 2])
        self.assertAlmostEqual(ranked[0].avg_rank, 1.0)
        self.assertAlmostEqual(ranked[1].avg_rank, 2.5)
        self.assertAlmostEqual(ranked[2].avg_rank, 2.5)

    def test_ties_share_the_same_position(self):
        ana, bruno, caio = make_players('ana', 'bruno', 'caio')
        voter = User.objects.create_user('voter', password=CREDENCIAL_DE_TESTE)

        Vote.objects.create(player=ana, voter=voter, rank=1)
        Vote.objects.create(player=bruno, voter=voter, rank=2)

        other = User.objects.create_user('other', password=CREDENCIAL_DE_TESTE)
        Vote.objects.create(player=bruno, voter=other, rank=1)
        Vote.objects.create(player=ana, voter=other, rank=2)
        Vote.objects.create(player=caio, voter=other, rank=3)

        ranked = rank_main_players()

        self.assertEqual(
            [(p.name, p.position) for p in ranked],
            [('ana', 1), ('bruno', 1), ('caio', 3)],
        )

    def test_players_without_votes_go_last(self):
        ana, bruno = make_players('ana', 'bruno')
        voter = User.objects.create_user('voter', password=CREDENCIAL_DE_TESTE)

        Vote.objects.create(player=bruno, voter=voter, rank=5)

        ranked = rank_main_players()

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
        self.ana = Player.objects.create(name='ana', is_main=True)
        self.bruno, self.caio = make_players('bruno', 'caio')
        self.client.force_login(self.voter)

        patcher = patch('players.decorators.is_voting_open', return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)

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

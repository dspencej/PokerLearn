from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql import func

db = SQLAlchemy()


class Game(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    game_number = db.Column(db.String(20), unique=True, nullable=False)
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.Time, nullable=False)
    hands = db.relationship("Hand", backref="game", lazy=True)
    num_players = db.Column(db.Integer)


class Hand(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey("game.id"), nullable=False)
    hand_number = db.Column(db.String(20), nullable=False)
    pots = db.relationship("Pot", backref="hand", lazy=True)
    rounds = db.relationship("Round", backref="hand", lazy=True)


class Round(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    hand_id = db.Column(db.Integer, db.ForeignKey("hand.id"), nullable=False)
    round_number = db.Column(db.Integer, nullable=False)
    round_name = db.Column(db.String(20), nullable=False)
    actions = db.relationship("PlayerAction", backref="round", lazy=True)
    board_cards = db.relationship("BoardCard", backref="round", lazy=True)
    starting_chips = db.Column(
        db.JSON, nullable=True
    )  # Stores starting chip counts for each player
    ending_chips = db.Column(
        db.JSON, nullable=True
    )  # Stores ending chip counts for each player
    total_bets = db.Column(db.Integer, nullable=True)  # Total amount bet in this round


class Player(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    seat_number = db.Column(db.Integer)
    chips_start = db.Column(db.Integer)
    total_chips_won = db.Column(db.Integer, default=0)
    total_chips_lost = db.Column(db.Integer, default=0)
    final_chip_count = db.Column(db.Integer)
    is_active = db.Column(db.Boolean, default=True)
    total_hands_played = db.Column(db.Integer, default=0)
    vpip_count = db.Column(db.Integer, default=0)  # Voluntarily Put Money In Pot
    pfr_count = db.Column(db.Integer, default=0)  # Preflop Raise
    uopfr_count = db.Column(db.Integer, default=0)  # Unopened Preflop Raise
    big_blinds_remaining = db.Column(db.Float, default=0.0)  # Big Blinds Remaining
    actions = db.relationship("PlayerAction", backref="player", lazy=True)

    @property
    def hands(self):
        hands = set()
        for action in self.actions:
            if action.round.hand:
                hands.add(action.round.hand)
        return list(hands)

    def recalculate_stats(self):
        self.total_chips_won = sum(
            action.amount for action in self.actions if action.action == "wins"
        )
        self.total_chips_lost = sum(
            action.amount for action in self.actions if action.action == "loses"
        )
        self.total_hands_played = (
            db.session.query(func.count(PlayerAction.id))
            .filter(PlayerAction.player_id == self.id)
            .scalar()
        )
        self.vpip_count = (
            db.session.query(func.count(PlayerAction.id))
            .filter(
                PlayerAction.player_id == self.id,
                PlayerAction.action.in_(["calls", "raises", "re-raises"]),
            )
            .scalar()
        )
        self.pfr_count = (
            db.session.query(func.count(PlayerAction.id))
            .filter(PlayerAction.player_id == self.id, PlayerAction.action == "raises")
            .scalar()
        )
        self.uopfr_count = (
            db.session.query(func.count(PlayerAction.id))
            .filter(
                PlayerAction.player_id == self.id,
                PlayerAction.action == "raises",
                PlayerAction.position == "UTG",
            )
            .scalar()
        )
        self.final_chip_count = (
            self.chips_start + self.total_chips_won - self.total_chips_lost
        )
        if self.final_chip_count:
            self.big_blinds_remaining = (
                self.final_chip_count / 100
            )  # Assuming 100 chips per big blind
        db.session.commit()


class PlayerAction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    round_id = db.Column(db.Integer, db.ForeignKey("round.id"), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey("player.id"), nullable=False)
    action = db.Column(db.String(20), nullable=False)
    amount = db.Column(db.Integer)
    position = db.Column(db.String(20))  # e.g., Small Blind, Big Blind, UTG
    is_all_in = db.Column(db.Boolean, default=False)


class BoardCard(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    round_id = db.Column(db.Integer, db.ForeignKey("round.id"), nullable=False)
    card = db.Column(db.String(2), nullable=False)
    card_position = db.Column(db.String(20))  # e.g., 1st Flop Card, Turn, River
    suit = db.Column(db.String(1))
    rank = db.Column(db.String(2))


class Pot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    hand_id = db.Column(db.Integer, db.ForeignKey("hand.id"), nullable=False)
    pot_type = db.Column(db.String(20))  # Main pot or side pot
    total_amount = db.Column(db.Integer)  # Total amount in the pot
    winners = db.relationship("PotWinner", backref="pot", lazy=True)


class PotWinner(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pot_id = db.Column(db.Integer, db.ForeignKey("pot.id"), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey("player.id"), nullable=False)
    amount_won = db.Column(db.Integer)  # Amount won by the player
    winning_hand = db.Column(db.String(20))  # Winning hand cards for this player

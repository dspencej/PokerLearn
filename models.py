from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    Float,
    ForeignKey,
    Integer,
    String,
    Time,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

Base = declarative_base()


class Game(Base):
    __tablename__ = "games"
    id = Column(Integer, primary_key=True, index=True)
    game_number = Column(String(20), unique=True, nullable=False)
    date = Column(Date, nullable=False)
    time = Column(Time, nullable=False)
    hands = relationship("Hand", backref="game", lazy=True)
    players = relationship("Player", backref="game", lazy=True)
    num_players = Column(Integer)

    def update_num_players(self, db):
        self.num_players = (
            db.query(func.count(func.distinct(Player.id)))
            .join(PlayerAction, Player.id == PlayerAction.player_id)
            .join(Round, Round.id == PlayerAction.round_id)
            .join(Hand, Hand.id == Round.hand_id)
            .filter(Hand.game_id == self.id)
            .scalar()
        )
        db.commit()


class Hand(Base):
    __tablename__ = "hands"
    id = Column(Integer, primary_key=True, index=True)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False)
    hand_number = Column(String(20), nullable=False)
    pots = relationship("Pot", backref="hand", lazy=True)
    rounds = relationship("Round", backref="hand", lazy=True)


class Round(Base):
    __tablename__ = "rounds"
    id = Column(Integer, primary_key=True, index=True)
    hand_id = Column(Integer, ForeignKey("hands.id"), nullable=False)
    round_number = Column(Integer, nullable=False)
    round_name = Column(String(20), nullable=False)
    actions = relationship("PlayerAction", backref="round", lazy=True)
    board_cards = relationship("BoardCard", backref="round", lazy=True)
    starting_chips = Column(
        JSON, nullable=True
    )  # Stores starting chip counts for each player
    ending_chips = Column(
        JSON, nullable=True
    )  # Stores ending chip counts for each player
    total_bets = Column(Integer, nullable=True)  # Total amount bet in this round


class Player(Base):
    __tablename__ = "players"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False)
    seat_number = Column(Integer)
    chips_start = Column(Integer)
    total_chips_won = Column(Integer, default=0)
    total_chips_lost = Column(Integer, default=0)
    final_chip_count = Column(Integer)
    is_active = Column(Boolean, default=True)
    total_hands_played = Column(Integer, default=0)
    vpip_count = Column(Integer, default=0)  # Voluntarily Put Money In Pot
    pfr_count = Column(Integer, default=0)  # Preflop Raise
    uopfr_count = Column(Integer, default=0)  # Unopened Preflop Raise
    big_blinds_remaining = Column(Float, default=0.0)  # Big Blinds Remaining
    actions = relationship("PlayerAction", backref="player", lazy=True)

    @property
    def hands(self):
        hands = set()
        for action in self.actions:
            if action.round.hand:
                hands.add(action.round.hand)
        return list(hands)

    def recalculate_stats(self, db):
        self.total_chips_won = sum(
            action.amount for action in self.actions if action.action == "wins"
        )
        self.total_chips_lost = sum(
            action.amount for action in self.actions if action.action == "loses"
        )
        self.total_hands_played = (
            db.query(func.count(PlayerAction.id))
            .filter(PlayerAction.player_id == self.id)
            .scalar()
        )
        self.vpip_count = (
            db.query(func.count(PlayerAction.id))
            .filter(
                PlayerAction.player_id == self.id,
                PlayerAction.action.in_(["calls", "raises", "re-raises"]),
            )
            .scalar()
        )
        self.pfr_count = (
            db.query(func.count(PlayerAction.id))
            .filter(PlayerAction.player_id == self.id, PlayerAction.action == "raises")
            .scalar()
        )
        self.uopfr_count = (
            db.query(func.count(PlayerAction.id))
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
        db.commit()


class PlayerAction(Base):
    __tablename__ = "player_actions"
    id = Column(Integer, primary_key=True, index=True)
    round_id = Column(Integer, ForeignKey("rounds.id"), nullable=False)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    action = Column(String(20), nullable=False)
    amount = Column(Integer)
    position = Column(String(20))  # e.g., Small Blind, Big Blind, UTG
    is_all_in = Column(Boolean, default=False)


class BoardCard(Base):
    __tablename__ = "board_cards"
    id = Column(Integer, primary_key=True, index=True)
    round_id = Column(Integer, ForeignKey("rounds.id"), nullable=False)
    card = Column(String(2), nullable=False)
    card_position = Column(String(20))  # e.g., 1st Flop Card, Turn, River
    suit = Column(String(1))
    rank = Column(String(2))


class Pot(Base):
    __tablename__ = "pots"
    id = Column(Integer, primary_key=True, index=True)
    hand_id = Column(Integer, ForeignKey("hands.id"), nullable=False)
    pot_type = Column(String(20))  # Main pot or side pot
    total_amount = Column(Integer)  # Total amount in the pot
    winners = relationship("PotWinner", backref="pot", lazy=True)


class PotWinner(Base):
    __tablename__ = "pot_winners"
    id = Column(Integer, primary_key=True, index=True)
    pot_id = Column(Integer, ForeignKey("pots.id"), nullable=False)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    amount_won = Column(Integer)  # Amount won by the player
    winning_hand = Column(String(20))  # Winning hand cards for this player

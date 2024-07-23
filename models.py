from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Game(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    game_number = db.Column(db.String(20), unique=True, nullable=False)
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.Time, nullable=False)
    hands = db.relationship('Hand', backref='game', lazy=True)

class Hand(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), nullable=False)
    hand_number = db.Column(db.String(20), nullable=False)
    rounds = db.relationship('Round', backref='hand', lazy=True)

class Round(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    hand_id = db.Column(db.Integer, db.ForeignKey('hand.id'), nullable=False)
    round_number = db.Column(db.Integer, nullable=False)
    round_name = db.Column(db.String(20), nullable=False)
    actions = db.relationship('PlayerAction', backref='round', lazy=True)
    board_cards = db.relationship('BoardCard', backref='round', lazy=True)

class Player(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    seat_number = db.Column(db.Integer)
    chips_start = db.Column(db.Integer)
    actions = db.relationship('PlayerAction', backref='player', lazy=True)

class PlayerAction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    round_id = db.Column(db.Integer, db.ForeignKey('round.id'), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    action = db.Column(db.String(20), nullable=False)
    amount = db.Column(db.Integer)

class BoardCard(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    round_id = db.Column(db.Integer, db.ForeignKey('round.id'), nullable=False)
    card = db.Column(db.String(2), nullable=False)

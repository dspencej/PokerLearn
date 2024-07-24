import argparse
import logging
import os
from datetime import datetime

from flask import Flask, jsonify, render_template
from flask_paginate import Pagination, get_page_args

from models import BoardCard, Game, Hand, Player, PlayerAction, Round, db
from parse_files import parse_files

# Create the /logs directory if it doesn't exist
log_dir = "./logs"
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

# Configure logging to write to a file and to the console
log_filename = datetime.now().strftime(f"{log_dir}/%d%m%y_%H%M%S.txt")
file_handler = logging.FileHandler(log_filename)
file_handler.setLevel(logging.DEBUG)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.ERROR)  # Only print ERROR messages to console

# Create a logging format
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

# Add the handlers to the logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Ensure the instance directory exists
instance_dir = os.path.abspath("./instance")
if not os.path.exists(instance_dir):
    os.makedirs(instance_dir)

app = Flask(__name__)
db_path = os.path.join(instance_dir, "poker_hands.db")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)


def initialize_db(persist):
    try:
        logger.debug(f"Database path: {db_path}")

        if not persist:
            if os.path.exists(db_path):
                os.remove(db_path)
                logger.debug("Removed existing database file.")

            with app.app_context():
                db.create_all()
                logger.debug("Created new database schema.")
                parse_files("data")
                logger.debug("Finished parsing files.")

        if persist and not os.path.exists(db_path):
            with app.app_context():
                db.create_all()
                logger.debug("Created new database schema.")
                parse_files("data")
                logger.debug("Finished parsing files.")
    except Exception as e:
        logger.error(f"Error initializing database. Error: {e}")


@app.route("/")
def index():
    try:
        page, per_page, offset = get_page_args(
            page_parameter="page", per_page_parameter="per_page"
        )
        total = Game.query.count()
        games = Game.query.offset(offset).limit(per_page).all()
        pagination = Pagination(
            page=page, per_page=per_page, total=total, css_framework="bootstrap4"
        )
        return render_template("index.html", games=games, pagination=pagination)
    except Exception as e:
        logger.error(f"Error fetching games for index page. Error: {e}")
        return "An error occurred."


@app.route("/game/<int:game_id>")
def game_details(game_id):
    try:
        game = db.session.get(Game, game_id)
        page, per_page, offset = get_page_args(
            page_parameter="page", per_page_parameter="per_page"
        )
        total = Hand.query.filter_by(game_id=game_id).count()
        hands = (
            Hand.query.filter_by(game_id=game_id).offset(offset).limit(per_page).all()
        )
        pagination = Pagination(
            page=page, per_page=per_page, total=total, css_framework="bootstrap4"
        )
        return render_template(
            "game_details.html", game=game, hands=hands, pagination=pagination
        )
    except Exception as e:
        logger.error(f"Error fetching game details for game_id: {game_id}. Error: {e}")
        return "An error occurred."


@app.route("/hand/<int:hand_id>")
def hand_details(hand_id):
    try:
        hand = db.session.get(Hand, hand_id)
        rounds = Round.query.filter_by(hand_id=hand_id).all()
        actions = PlayerAction.query.join(Round).filter(Round.hand_id == hand_id).all()
        board_cards = BoardCard.query.join(Round).filter(Round.hand_id == hand_id).all()
        return render_template(
            "hand_details.html", hand=hand, actions=actions, board_cards=board_cards
        )
    except Exception as e:
        logger.error(f"Error fetching hand details for hand_id: {hand_id}. Error: {e}")
        return "An error occurred."


@app.route("/player/<int:player_id>")
def player_details(player_id):
    try:
        player = db.session.get(Player, player_id)
        actions = PlayerAction.query.filter_by(player_id=player_id).all()
        return render_template("player_details.html", player=player, actions=actions)
    except Exception as e:
        logger.error(
            f"Error fetching player details for player_id: {player_id}. Error: {e}"
        )
        return "An error occurred."


@app.route("/reset_db")
def reset_db():
    try:
        # Close the existing database session
        db.session.remove()
        # Dispose of the existing database engine
        db.engine.dispose()

        if os.path.exists("instance/poker_hands.db"):
            os.remove("instance/poker_hands.db")
            logger.info("Deleted existing database.")
        db.create_all()
        logger.info("Created new database.")
        from parse_files import parse_files

        parse_files("data")
        return jsonify(success=True)
    except Exception as e:
        logger.error(f"Error resetting database. Error: {e}")
        return jsonify(success=False, error=str(e))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Poker Hand History Processor")
    parser.add_argument(
        "-p", "--persist", action="store_true", help="Persist the database"
    )
    args = parser.parse_args()

    initialize_db(args.persist)

    try:
        app.run(debug=True)
    except Exception as e:
        logger.error(f"Error running the Flask app. Error: {e}")

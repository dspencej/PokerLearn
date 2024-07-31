import logging
import os
from datetime import datetime

from sqlalchemy.orm import Session
from tqdm import tqdm

from database import SessionLocal
from models import BoardCard, Game, Hand, Player, PlayerAction, Round

log_dir = "./logs"
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

# Configure logging to write to a file and to the console
log_filename = datetime.now().strftime(f"{log_dir}/%d%m%y_%H%M%S.txt")
file_handler = logging.FileHandler(log_filename)
file_handler.setLevel(logging.DEBUG)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.ERROR)

# Create a logging format
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

# Add the handlers to the logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(file_handler)
logger.addHandler(console_handler)

ROUND_NAMES = {1: "Pre-Flop", 2: "Flop", 3: "Turn", 4: "River", 5: "Showdown"}


def extract_amount(text):
    try:
        if "[" in text and "]" in text:
            return int(text.split("[")[1].split(" ")[0].replace(",", ""))
        elif "posted ante" in text:
            return int(
                text.rsplit("ante of")[1].rsplit("Tournament")[0].replace(",", "")
            )
        return 0  # No amount to extract
    except Exception as e:
        logger.error(f"Error extracting amount from text: {text}. Error: {e}")
        return None


def extract_player_name_and_action(line, action_keywords):
    for action in action_keywords:
        if action in line:
            player_name = line.rsplit(action, 1)[0].strip()
            return player_name, action
    return None, None


def extract_blinds(line):
    try:
        parts = line.split(" ")
        sb = int(parts[parts.index("Small") + 2])
        bb = int(parts[parts.index("Big") + 2])
        return sb, bb
    except Exception as e:
        logger.error(f"Error extracting blinds from text: {line}. Error: {e}")
        return None, None


def process_game_start_line(line, game_id, db: Session):
    hand_number = line.split("#")[1].split("starts")[0].strip()
    hand = Hand(game_id=game_id, hand_number=hand_number)
    db.add(hand)
    db.commit()
    db.refresh(hand)
    if hand.id is None:
        raise ValueError("Hand creation failed; id is None")
    logger.debug(f"Created new hand entry {hand_number} for game {game_id}")
    return hand


def create_new_round(hand_id, round_number, db: Session):
    round_name = ROUND_NAMES.get(round_number, f"Round {round_number}")
    new_round = Round(hand_id=hand_id, round_number=round_number, round_name=round_name)
    db.add(new_round)
    db.commit()
    db.refresh(new_round)
    if new_round.id is None:
        raise ValueError("Round creation failed; id is None")
    logger.debug(f"Created new round entry {round_name} for hand {hand_id}")
    return new_round


def process_player_action_line(line, round_entry, game_number, hand, db: Session):
    try:
        action_keywords = [
            "re-raises",
            "posts",
            "calls",
            "raises",
            "folds",
            "posted ante",
        ]
        player_name, action = extract_player_name_and_action(line, action_keywords)
        if not player_name or not action:
            raise ValueError("No valid action found in line")

        amount = extract_amount(line)

        player_record = db.query(Player).filter_by(name=player_name).first()
        if not player_record:
            # Add player dynamically if not found
            player_record = Player(
                name=player_name, game_id=hand.game_id, seat_number=-1, chips_start=0
            )
            db.add(player_record)
            db.commit()
            db.refresh(player_record)
            if player_record.id is None:
                raise ValueError(
                    f"Player creation failed for {player_name}; id is None"
                )
            logger.debug(f"Created new player entry {player_name} dynamically")

        player_action = PlayerAction(
            round_id=round_entry.id,
            player_id=player_record.id,
            action=action,
            amount=amount,
        )
        db.add(player_action)
        logger.debug(
            f"Added action {action} by player {player_name} for {amount} chips in round {round_entry.round_name} for hand {hand.hand_number} in game {game_number}"
        )

        # Update player statistics
        if action in ["re-raises", "calls", "raises"]:
            player_record.vpip_count += 1  # Increment VPIP count
            if round_entry.round_name == "Pre-Flop":
                player_record.pfr_count += (
                    1 if action in ["re-raises", "raises"] else 0
                )  # Increment PFR count
                player_record.uopfr_count += (
                    1 if action == "raises" else 0
                )  # Increment UOPFR count

    except Exception as e:
        logger.error(f"Error processing player action line: {line}. Error: {e}")


def process_show_action_line(line, round_entry, game_number, hand, db: Session):
    try:
        action = "shows"
        parts = line.split("shows")
        player_name = parts[0].strip()
        amount = 0  # No amount for show action
        player_record = db.query(Player).filter_by(name=player_name).first()
        if player_record:
            player_action = PlayerAction(
                round_id=round_entry.id,
                player_id=player_record.id,
                action=action,
                amount=amount,
            )
            db.add(player_action)
            logger.debug(
                f"Player {player_name} shows cards in round {round_entry.round_name} for hand {hand.hand_number} in game {game_number}"
            )
        else:
            logger.error(
                f"Player record not found for {player_name} when processing show line: {line}"
            )
    except Exception as e:
        logger.error(f"Error processing show action line: {line}. Error: {e}")


def process_seat_line(line, hand, game_number, round_entry, db: Session):
    try:
        parts = line.split(": ")
        seat_info = parts[0].split(" ")
        seat = int(seat_info[1])
        player_info = parts[1].split(" (")
        player = player_info[0].strip()
        chips = int(player_info[1].split(" ")[0].replace(",", ""))

        player_record = db.query(Player).filter_by(name=player).first()
        if not player_record:
            player_record = Player(
                name=player, game_id=hand.game_id, seat_number=seat, chips_start=chips
            )
            db.add(player_record)
            db.commit()
            db.refresh(player_record)
            if player_record.id is None:
                raise ValueError(f"Player creation failed for {player}; id is None")
            logger.debug(
                f"Created new player entry {player} at seat {seat} with {chips} chips in hand {hand.hand_number} for game {game_number}"
            )
        player_action = PlayerAction(
            round_id=round_entry.id,
            player_id=player_record.id,
            action="seat",
            amount=chips,
        )
        db.add(player_action)
        logger.debug(
            f"Added seat action for player {player} with {chips} chips in round {round_entry.round_name} for hand {hand.hand_number} in game {game_number}"
        )
    except Exception as e:
        logger.error(f"Error processing seat line: {line}. Error: {e}")


def process_dealing_line(line, round_entry, game_number, hand, db: Session):
    card = line.split("[")[1].split("]")[0]
    board_card = BoardCard(round_id=round_entry.id, card=card)
    db.add(board_card)
    logger.debug(
        f"Dealt card {card} for round {round_entry.round_name} in hand {hand.hand_number} for game {game_number}"
    )


def process_player_leaves_line(line, db: Session):
    parts = line.split(" ")
    player_name = " ".join(parts[1 : parts.index("leaves")])
    player_record = db.query(Player).filter_by(name=player_name).first()
    if player_record:
        logger.debug(
            f"Player {player_name} leaves the table with {player_record.chips_start} chips"
        )
    else:
        logger.error(
            f"Player record not found for {player_name} when processing leave line: {line}"
        )


def parse_lines(lines, game_number, game_id, db: Session):
    hand = None
    round_entry = None
    game_started = False
    hand_started = False
    round_number = 1

    for line in lines:
        if line.startswith("Game #") and "starts" in line:
            game_started = True
            hand_started = True

        if not game_started:
            continue

        try:
            if line.startswith("Game #") and "starts" in line:
                if hand:
                    db.commit()
                    logger.debug(
                        f"Committed hand {hand.hand_number} for game {game_number}"
                    )
                hand = process_game_start_line(line, game_id, db)
                round_entry = create_new_round(hand.id, round_number, db)
            elif "blinds are" in line:
                small_blind, big_blind = extract_blinds(line)
                if hand:
                    hand.small_blind = small_blind
                    hand.big_blind_value = big_blind
                    db.commit()
                    logger.debug(
                        f"Set blinds for hand {hand.hand_number}: small_blind={small_blind}, big_blind={big_blind}"
                    )
            elif line.startswith("Game #") and "ends" in line:
                db.commit()
                logger.debug(
                    f"Committed hand {hand.hand_number} for game {game_number}"
                )
                hand = None
                hand_started = False
                round_number = 1  # Reset round number for the next hand
            elif hand_started and line.startswith("Round") and "is over" in line:
                round_number += 1
                round_entry = create_new_round(hand.id, round_number, db)
                logger.debug(
                    f"Round {round_number} is over, created new round entry for hand {hand.hand_number} in game {game_number}"
                )
            elif hand_started and "** Dealing" in line:
                process_dealing_line(line, round_entry, game_number, hand, db)
            elif hand_started and line.startswith("Seat"):
                process_seat_line(line, hand, game_number, round_entry, db)
            elif hand_started and any(
                action in line
                for action in [
                    "re-raises",
                    "posts",
                    "calls",
                    "raises",
                    "folds",
                    "posted ante",
                ]
            ):
                process_player_action_line(line, round_entry, game_number, hand, db)
            elif hand_started and "shows" in line:
                process_show_action_line(line, round_entry, game_number, hand, db)
            elif line.startswith("Player") and "leaves the table" in line:
                process_player_leaves_line(line, db)
        except Exception as e:
            logger.error(f"Error processing line: {line}. Error: {e}")
            db.rollback()  # Rollback the session to handle subsequent lines correctly
    if hand:
        db.commit()
        logger.debug(f"Committed hand {hand.hand_number} for game {game_number}")


def parse_files(data_folder):
    try:
        files = [f for f in os.listdir(data_folder) if f.endswith(".txt")]
        for file in tqdm(files, desc="Processing Files"):
            logger.debug(f"Processing file: {file}")
            with open(os.path.join(data_folder, file), "r") as f:
                lines = f.readlines()
                game_number = lines[0].split("#: ")[1].strip()
                logger.debug(f"Found game number: {game_number}")

                # Extract game date and time from filename
                filename = os.path.splitext(file)[0]
                filename_parts = filename.split(" ")
                date_str = filename_parts[-2].split("History-")[-1]
                time_str = filename_parts[-1].replace("_", ":")
                game_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                game_time = datetime.strptime(time_str, "%H:%M:%S").time()

                db = SessionLocal()

                try:
                    game = db.query(Game).filter_by(game_number=game_number).first()
                    if not game:
                        game = Game(
                            game_number=game_number, date=game_date, time=game_time
                        )
                        db.add(game)
                        db.commit()
                        db.refresh(game)
                        logger.debug(
                            f"Created new game entry: {game_number} with date: {game_date} and time: {game_time}"
                        )
                    else:
                        logger.debug(
                            f"Game {game_number} already exists in the database. Processing hands..."
                        )

                    parse_lines(lines[1:], game_number, game.id, db)
                    game.update_num_players(db)
                finally:
                    db.close()
    except Exception as e:
        logger.error(f"Error processing files in folder: {data_folder}. Error: {e}")

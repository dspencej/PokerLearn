import argparse
import logging
import os
from datetime import datetime

import uvicorn
from fastapi import Depends, FastAPI, File, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi_pagination import Params, add_pagination
from fastapi_pagination.ext.sqlalchemy import paginate
from sqlalchemy.orm import Session, joinedload

from database import SessionLocal, engine
from models import Base, BoardCard, Game, Hand, Player, PlayerAction, Round
from parse_files import parse_files

# Initialize the application
app = FastAPI()
add_pagination(app)

# Setup Jinja2 templates
templates = Jinja2Templates(directory="templates")

# Configure logging
log_dir = "./logs"
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

log_filename = datetime.now().strftime(f"{log_dir}/%d%m%y_%H%M%S.txt")
file_handler = logging.FileHandler(log_filename)
file_handler.setLevel(logging.DEBUG)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.ERROR)

formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Initialize the database
Base.metadata.create_all(bind=engine)


# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Function to initialize the database
def initialize_db(persist):
    try:
        logger.debug(f"Database path: {engine.url}")

        if not persist:
            # Ensure the database session is closed before attempting to remove the file
            db = SessionLocal()
            db.close()
            engine.dispose()

            if os.path.exists(engine.url.database):
                os.remove(engine.url.database)
                logger.debug("Removed existing database file.")
            Base.metadata.create_all(bind=engine)
            logger.debug("Created new database schema.")
            parse_files("data")
            logger.debug("Finished parsing files.")

        if persist and not os.path.exists(engine.url.database):
            Base.metadata.create_all(bind=engine)
            logger.debug("Created new database schema.")
            parse_files("data")
            logger.debug("Finished parsing files.")
    except Exception as e:
        logger.error(f"Error initializing database. Error: {e}")


@app.get("/", response_class=HTMLResponse)
async def index(
    request: Request, db: Session = Depends(get_db), params: Params = Depends()
):
    try:
        games_query = db.query(Game)
        games = paginate(games_query, params)
        logger.debug(f"Retrieved games: {games.items}")
        return templates.TemplateResponse(
            "index.html", {"request": request, "games": games}
        )
    except Exception as e:
        logger.error(f"Error fetching games for index page. Error: {e}")
        return HTMLResponse("An error occurred.", status_code=500)


@app.get("/game/{game_id}", response_class=HTMLResponse)
async def game_details(
    request: Request,
    game_id: int,
    db: Session = Depends(get_db),
    params: Params = Depends(),
):
    try:
        game = db.query(Game).filter(Game.id == game_id).first()
        if not game:
            logger.error(f"Game with id {game_id} not found.")
            return HTMLResponse("Game not found.", status_code=404)

        hands_query = (
            db.query(Hand)
            .filter(Hand.game_id == game_id)
            .options(joinedload(Hand.rounds))
        )
        hands = paginate(hands_query, params)

        logger.debug(f"Retrieved hands for game {game_id}: {hands.items}")
        return templates.TemplateResponse(
            "game_details.html", {"request": request, "game": game, "hands": hands}
        )
    except Exception as e:
        logger.error(f"Error fetching game details for game_id: {game_id}. Error: {e}")
        return HTMLResponse("An error occurred.", status_code=500)


@app.get("/hand/{hand_id}", response_class=HTMLResponse)
async def hand_details(
    request: Request,
    hand_id: int,
    db: Session = Depends(get_db),
    params: Params = Depends(),
):
    try:
        hand = db.query(Hand).filter(Hand.id == hand_id).first()
        if not hand:
            logger.error(f"Hand with id {hand_id} not found.")
            return HTMLResponse("Hand not found.", status_code=404)

        rounds = db.query(Round).filter(Round.hand_id == hand_id).all()
        round_ids = [r.id for r in rounds]

        actions_query = (
            db.query(PlayerAction)
            .filter(PlayerAction.round_id.in_(round_ids))
            .options(joinedload(PlayerAction.player), joinedload(PlayerAction.round))
        )
        actions = paginate(actions_query, params)

        board_cards_query = (
            db.query(BoardCard)
            .filter(BoardCard.round_id.in_(round_ids))
            .options(joinedload(BoardCard.round))
        )
        board_cards = paginate(board_cards_query, params)

        logger.debug(
            f"Retrieved details for hand {hand_id}: rounds {rounds}, actions {actions.items}, board cards {board_cards.items}"
        )
        return templates.TemplateResponse(
            "hand_details.html",
            {
                "request": request,
                "hand": hand,
                "rounds": rounds,
                "actions": actions.items,
                "board_cards": board_cards.items,
            },
        )
    except Exception as e:
        logger.error(f"Error fetching hand details for hand_id: {hand_id}. Error: {e}")
        return HTMLResponse("An error occurred.", status_code=500)


@app.get("/player/{player_id}", response_class=HTMLResponse)
async def player_details(
    request: Request,
    player_id: int,
    db: Session = Depends(get_db),
    params: Params = Depends(),
):
    try:
        player = db.query(Player).filter(Player.id == player_id).first()
        if not player:
            logger.error(f"Player with id {player_id} not found.")
            return HTMLResponse("Player not found.", status_code=404)

        actions_query = (
            db.query(PlayerAction)
            .filter(PlayerAction.player_id == player_id)
            .options(joinedload(PlayerAction.round).joinedload(Round.hand))
        )
        actions = paginate(actions_query, params)

        logger.debug(f"Retrieved actions for player {player_id}: {actions.items}")
        return templates.TemplateResponse(
            "player_details.html",
            {"request": request, "player": player, "actions": actions.items},
        )
    except Exception as e:
        logger.error(
            f"Error fetching player details for player_id: {player_id}. Error: {e}"
        )
        return HTMLResponse("An error occurred.", status_code=500)


@app.get("/player/{player_id}/recalculate_stats", response_class=JSONResponse)
async def recalculate_stats(player_id: int, db: Session = Depends(get_db)):
    try:
        player = db.query(Player).filter(Player.id == player_id).first()
        if not player:
            logger.error(f"Player with id {player_id} not found.")
            return JSONResponse({"success": False, "error": "Player not found"})

        player.recalculate_stats(db)
        logger.info(f"Recalculated stats for player {player.name}")
        return JSONResponse({"success": True})
    except Exception as e:
        logger.error(
            f"Error recalculating stats for player_id: {player_id}. Error: {e}"
        )
        return JSONResponse({"success": False, "error": str(e)})


@app.get("/walkthrough/{game_id}/{hand_id}", response_class=HTMLResponse)
async def walkthrough(
    request: Request,
    game_id: int,
    hand_id: int,
    db: Session = Depends(get_db),
    params: Params = Depends(),
):
    try:
        game = db.query(Game).filter(Game.id == game_id).first()
        hand = db.query(Hand).filter(Hand.id == hand_id).first()
        if not game or not hand:
            logger.error(f"Game with id {game_id} or Hand with id {hand_id} not found.")
            return HTMLResponse("Game or Hand not found.", status_code=404)

        actions = paginate(
            db.query(PlayerAction)
            .join(Round)
            .filter(Round.hand_id == hand_id)
            .order_by(PlayerAction.id),
            params,
        )
        serialized_actions = [
            {
                "id": action.id,
                "player": {
                    "name": action.player.name,
                    "seat_number": action.player.seat_number,
                },
                "round": {"round_name": action.round.round_name},
                "action": action.action,
                "amount": action.amount,
                "position": action.position,
                "is_all_in": action.is_all_in,
            }
            for action in actions.items
        ]
        logger.debug(
            f"Retrieved actions for game {game_id}, hand {hand_id}: {serialized_actions}"
        )
        return templates.TemplateResponse(
            "walkthrough.html",
            {
                "request": request,
                "game": game,
                "hand": hand,
                "actions": serialized_actions,
            },
        )
    except Exception as e:
        logger.error(
            f"Error fetching walkthrough details for game_id: {game_id}, hand_id: {hand_id}. Error: {e}"
        )
        return HTMLResponse("An error occurred.", status_code=500)


@app.get("/reset_db", response_class=JSONResponse)
async def reset_db():
    try:
        # Close the existing database session
        db = SessionLocal()
        db.close()
        # Dispose of the existing database engine
        engine.dispose()

        if os.path.exists("instance/poker_hands.db"):
            os.remove("instance/poker_hands.db")
            logger.info("Deleted existing database.")
        Base.metadata.create_all(bind=engine)
        logger.info("Created new database.")
        parse_files("data")
        return JSONResponse({"success": True})
    except Exception as e:
        logger.error(f"Error resetting database. Error: {e}")
        return JSONResponse({"success": False, "error": str(e)})


@app.post("/uploadfile/")
async def upload_file(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        with open(os.path.join("data", file.filename), "wb") as f:
            f.write(contents)
        parse_files("data")
        return {"filename": file.filename, "status": "file processed successfully"}
    except Exception as e:
        logger.error(f"Error uploading file. Error: {e}")
        return JSONResponse({"success": False, "error": str(e)})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Poker Hand History Processor")
    parser.add_argument(
        "-p", "--persist", action="store_true", help="Persist the database"
    )
    args = parser.parse_args()

    initialize_db(args.persist)

    uvicorn.run(app, host="127.0.0.1", port=8000)

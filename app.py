import argparse
import logging
import os
from datetime import datetime

from fastapi import Depends, FastAPI, File, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi_pagination import Params
from fastapi_pagination.ext.sqlalchemy import paginate as sqlalchemy_paginate
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import Base, SessionLocal, engine
from models import BoardCard, Game, Hand, Player, PlayerAction, Round
from parse_files import parse_files

# Initialize the application
app = FastAPI()

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

# Ensure the instance directory exists
if not os.path.exists("./instance"):
    os.makedirs("./instance")

# Initialize the database
Base.metadata.create_all(bind=engine)


# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def initialize_db(persist):
    try:
        logger.debug(f"Database path: {engine.url.database}")

        if not persist:
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


# Routes
@app.get("/", response_class=HTMLResponse)
async def index(
    request: Request, db: Session = Depends(get_db), params: Params = Depends()
):
    try:
        games = sqlalchemy_paginate(db.execute(select(Game)).scalars(), params)
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
        game = db.execute(select(Game).filter_by(id=game_id)).scalar_one_or_none()
        hands = sqlalchemy_paginate(
            db.execute(select(Hand).filter_by(game_id=game_id)).scalars(), params
        )
        return templates.TemplateResponse(
            "game_details.html", {"request": request, "game": game, "hands": hands}
        )
    except Exception as e:
        logger.error(f"Error fetching game details for game_id: {game_id}. Error: {e}")
        return HTMLResponse("An error occurred.", status_code=500)


@app.get("/hand/{hand_id}", response_class=HTMLResponse)
async def hand_details(request: Request, hand_id: int, db: Session = Depends(get_db)):
    try:
        hand = db.execute(select(Hand).filter_by(id=hand_id)).scalar_one_or_none()
        rounds = db.execute(select(Round).filter_by(hand_id=hand_id)).scalars().all()
        actions = (
            db.execute(
                select(PlayerAction).join(Round).filter(Round.hand_id == hand_id)
            )
            .scalars()
            .all()
        )
        board_cards = (
            db.execute(select(BoardCard).join(Round).filter(Round.hand_id == hand_id))
            .scalars()
            .all()
        )
        return templates.TemplateResponse(
            "hand_details.html",
            {
                "request": request,
                "hand": hand,
                "actions": actions,
                "board_cards": board_cards,
            },
        )
    except Exception as e:
        logger.error(f"Error fetching hand details for hand_id: {hand_id}. Error: {e}")
        return HTMLResponse("An error occurred.", status_code=500)


@app.get("/player/{player_id}", response_class=HTMLResponse)
async def player_details(
    request: Request, player_id: int, db: Session = Depends(get_db)
):
    try:
        player = db.execute(select(Player).filter_by(id=player_id)).scalar_one_or_none()
        actions = (
            db.execute(select(PlayerAction).filter_by(player_id=player_id))
            .scalars()
            .all()
        )
        return templates.TemplateResponse(
            "player_details.html",
            {"request": request, "player": player, "actions": actions},
        )
    except Exception as e:
        logger.error(
            f"Error fetching player details for player_id: {player_id}. Error: {e}"
        )
        return HTMLResponse("An error occurred.", status_code=500)


@app.get("/player/{player_id}/recalculate_stats", response_class=JSONResponse)
async def recalculate_stats(player_id: int, db: Session = Depends(get_db)):
    try:
        player = db.execute(select(Player).filter_by(id=player_id)).scalar_one_or_none()
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
    request: Request, game_id: int, hand_id: int, db: Session = Depends(get_db)
):
    try:
        game = db.execute(select(Game).filter_by(id=game_id)).scalar_one_or_none()
        hand = db.execute(select(Hand).filter_by(id=hand_id)).scalar_one_or_none()
        actions = (
            db.execute(
                select(PlayerAction)
                .join(Round)
                .filter(Round.hand_id == hand_id)
                .order_by(PlayerAction.id)
            )
            .scalars()
            .all()
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
            for action in actions
        ]
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

        if os.path.exists("./instance/poker_hands.db"):
            os.remove("./instance/poker_hands.db")
            logger.info("Deleted existing database.")
        Base.metadata.create_all(bind=engine)
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

    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)

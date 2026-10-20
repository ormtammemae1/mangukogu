from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, func, or_, select

from . import database
from .database import get_session, init_db
from .images import BadImage, delete_image, save_image
from .models import (
    Category,
    CategoryCreate,
    CategoryRead,
    CategoryUpdate,
    Game,
    GameCategory,
    GameCategoryRef,
    GameCreate,
    GameRead,
    GameUpdate,
    utcnow,
)

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Mängukogu", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

SessionDep = Annotated[Session, Depends(get_session)]


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/manifest.webmanifest", include_in_schema=False)
def manifest():
    return FileResponse(STATIC_DIR / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/images/{name}", include_in_schema=False)
def image(name: str):
    path = database.IMAGE_DIR / name
    if "/" in name or ".." in name or not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    # File names are random and never reused, so they can be cached for good.
    return FileResponse(path, headers={"Cache-Control": "public, max-age=31536000, immutable"})


# ---- Categories ----

def _get_category_or_404(session: Session, category_id: int) -> Category:
    category = session.get(Category, category_id)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    return category


def _commit_category(session: Session, category: Category) -> None:
    session.add(category)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "A category with this name already exists")
    session.refresh(category)


@app.get("/api/categories", response_model=list[CategoryRead])
def list_categories(session: SessionDep):
    counts = dict(
        session.exec(select(GameCategory.category_id, func.count()).group_by(GameCategory.category_id)).all()
    )
    categories = session.exec(select(Category).order_by(Category.position, Category.name)).all()
    return [CategoryRead(id=c.id, name=c.name, game_count=counts.get(c.id, 0)) for c in categories]


@app.post("/api/categories", response_model=CategoryRead, status_code=status.HTTP_201_CREATED)
def create_category(data: CategoryCreate, session: SessionDep):
    last = session.exec(select(func.max(Category.position))).one()
    category = Category(name=data.name, position=(last or 0) + 1)
    _commit_category(session, category)
    return CategoryRead(id=category.id, name=category.name)


@app.put("/api/categories/{category_id}", response_model=CategoryRead)
def update_category(category_id: int, data: CategoryUpdate, session: SessionDep):
    category = _get_category_or_404(session, category_id)
    category.name = data.name
    _commit_category(session, category)
    return CategoryRead(id=category.id, name=category.name, game_count=len(category.games))


@app.delete("/api/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(category_id: int, session: SessionDep):
    """Remove the category; its games stay, they just lose this label."""
    session.delete(_get_category_or_404(session, category_id))
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---- Games ----

def _to_read(game: Game) -> GameRead:
    return GameRead(
        id=game.id,
        name=game.name,
        notes=game.notes,
        age_min=game.age_min,
        age_max=game.age_max,
        image_url=f"/images/{game.image}" if game.image else None,
        thumb_url=f"/images/thumb-{game.image}" if game.image else None,
        categories=[
            GameCategoryRef(id=c.id, name=c.name)
            for c in sorted(game.categories, key=lambda c: (c.position, c.name))
        ],
        created_at=game.created_at,
        updated_at=game.updated_at,
    )


def _get_game_or_404(session: Session, game_id: int) -> Game:
    game = session.get(Game, game_id)
    if game is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Game not found")
    return game


def _load_categories(session: Session, ids: list[int]) -> list[Category]:
    ids = list(dict.fromkeys(ids))
    if not ids:
        return []
    found = session.exec(select(Category).where(col(Category.id).in_(ids))).all()
    if len(found) != len(ids):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown category")
    return list(found)


@app.get("/api/games", response_model=list[GameRead])
def list_games(
    session: SessionDep,
    q: str | None = Query(None, description="Search name and notes"),
    category: int | None = Query(None, description="Only games in this category"),
    age: int | None = Query(None, description="Only games suitable for this age (games without an age always match)"),
):
    stmt = select(Game)
    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(col(Game.name).ilike(like), col(Game.notes).ilike(like)))
    if category is not None:
        stmt = stmt.where(
            col(Game.id).in_(select(GameCategory.game_id).where(GameCategory.category_id == category))
        )
    if age is not None:
        stmt = stmt.where(
            or_(col(Game.age_min).is_(None), col(Game.age_min) <= age),
            or_(col(Game.age_max).is_(None), col(Game.age_max) >= age),
        )
    stmt = stmt.order_by(func.lower(Game.name))
    return [_to_read(g) for g in session.exec(stmt).all()]


@app.get("/api/games/{game_id}", response_model=GameRead)
def get_game(game_id: int, session: SessionDep):
    return _to_read(_get_game_or_404(session, game_id))


@app.post("/api/games", response_model=GameRead, status_code=status.HTTP_201_CREATED)
def create_game(data: GameCreate, session: SessionDep):
    game = Game.model_validate(data.model_dump(exclude={"category_ids"}))
    game.categories = _load_categories(session, data.category_ids)
    session.add(game)
    session.commit()
    session.refresh(game)
    return _to_read(game)


@app.put("/api/games/{game_id}", response_model=GameRead)
def update_game(game_id: int, data: GameUpdate, session: SessionDep):
    game = _get_game_or_404(session, game_id)
    game.sqlmodel_update(data.model_dump(exclude={"category_ids"}))
    game.categories = _load_categories(session, data.category_ids)
    game.updated_at = utcnow()
    session.add(game)
    session.commit()
    session.refresh(game)
    return _to_read(game)


@app.delete("/api/games/{game_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_game(game_id: int, session: SessionDep):
    game = _get_game_or_404(session, game_id)
    image_name = game.image
    session.delete(game)
    session.commit()
    delete_image(image_name, database.IMAGE_DIR)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.put("/api/games/{game_id}/image", response_model=GameRead)
async def upload_image(game_id: int, file: UploadFile, session: SessionDep):
    game = _get_game_or_404(session, game_id)
    try:
        name = save_image(await file.read(), database.IMAGE_DIR)
    except BadImage:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Could not read the picture")
    old = game.image
    game.image = name
    game.updated_at = utcnow()
    session.add(game)
    session.commit()
    session.refresh(game)
    delete_image(old, database.IMAGE_DIR)
    return _to_read(game)


@app.delete("/api/games/{game_id}/image", response_model=GameRead)
def remove_image(game_id: int, session: SessionDep):
    game = _get_game_or_404(session, game_id)
    old = game.image
    game.image = None
    game.updated_at = utcnow()
    session.add(game)
    session.commit()
    session.refresh(game)
    delete_image(old, database.IMAGE_DIR)
    return _to_read(game)

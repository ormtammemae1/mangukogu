from datetime import datetime, timezone

from pydantic import field_validator, model_validator
from sqlmodel import Field, Relationship, SQLModel

MIN_AGE = 1
MAX_AGE = 7


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    value = " ".join(value.split())
    return value or None


class GameCategory(SQLModel, table=True):
    game_id: int = Field(foreign_key="game.id", primary_key=True, ondelete="CASCADE")
    category_id: int = Field(foreign_key="category.id", primary_key=True, ondelete="CASCADE")


# ---- Categories ----

class CategoryBase(SQLModel):
    name: str = Field(min_length=1, max_length=80)

    @field_validator("name", mode="before")
    @classmethod
    def _clean_name(cls, v):
        return clean_text(v) if isinstance(v, str) else v


class Category(CategoryBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=80, unique=True)
    position: int = 0
    games: list["Game"] = Relationship(back_populates="categories", link_model=GameCategory)


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(CategoryBase):
    pass


class CategoryRead(SQLModel):
    id: int
    name: str
    game_count: int = 0


# ---- Games ----

class GameFields(SQLModel):
    name: str = Field(min_length=1, max_length=120)
    notes: str | None = Field(default=None, max_length=5000)
    age_min: int | None = Field(default=None, ge=MIN_AGE, le=MAX_AGE)
    age_max: int | None = Field(default=None, ge=MIN_AGE, le=MAX_AGE)

    @field_validator("name", mode="before")
    @classmethod
    def _clean_name(cls, v):
        return clean_text(v) if isinstance(v, str) else v

    @field_validator("notes", mode="before")
    @classmethod
    def _clean_notes(cls, v):
        # Keep the teacher's line breaks; only trim the ends.
        if isinstance(v, str):
            v = v.strip()
            return v or None
        return v

    @model_validator(mode="after")
    def _ages_in_order(self):
        if self.age_min is not None and self.age_max is not None and self.age_min > self.age_max:
            self.age_min, self.age_max = self.age_max, self.age_min
        return self


class Game(GameFields, table=True):
    id: int | None = Field(default=None, primary_key=True)
    image: str | None = None  # file name in IMAGE_DIR; thumbnail is "thumb-" + image
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    categories: list[Category] = Relationship(back_populates="games", link_model=GameCategory)


class GameCreate(GameFields):
    category_ids: list[int] = []


class GameUpdate(GameFields):
    category_ids: list[int] = []


class GameCategoryRef(SQLModel):
    id: int
    name: str


class GameRead(SQLModel):
    id: int
    name: str
    notes: str | None
    age_min: int | None
    age_max: int | None
    image_url: str | None
    thumb_url: str | None
    categories: list[GameCategoryRef]
    created_at: datetime
    updated_at: datetime

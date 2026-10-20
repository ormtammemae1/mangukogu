import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app import database
from app.database import DEFAULT_CATEGORIES, get_session
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(database, "IMAGE_DIR", tmp_path / "images")
    SQLModel.metadata.create_all(engine)

    def session_override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _jpeg(size=(2400, 1200)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, "orange").save(buf, "JPEG")
    return buf.getvalue()


def _cat_id(client, name):
    return next(c["id"] for c in client.get("/api/categories").json() if c["name"] == name)


def test_default_categories_seeded_in_order(client):
    names = [c["name"] for c in client.get("/api/categories").json()]
    assert names == DEFAULT_CATEGORIES


def test_add_rename_delete_category(client):
    r = client.post("/api/categories", json={"name": "  Rütmitunne  "})
    assert r.status_code == 201
    cat = r.json()
    assert cat["name"] == "Rütmitunne"
    assert client.get("/api/categories").json()[-1]["name"] == "Rütmitunne"

    assert client.post("/api/categories", json={"name": "Rütmitunne"}).status_code == 409
    assert client.post("/api/categories", json={"name": "   "}).status_code == 422

    r = client.put(f"/api/categories/{cat['id']}", json={"name": "Rütm"})
    assert r.json()["name"] == "Rütm"
    assert client.delete(f"/api/categories/{cat['id']}").status_code == 204
    assert "Rütm" not in [c["name"] for c in client.get("/api/categories").json()]


def test_create_game_with_categories_and_ages(client):
    loogika, sort = _cat_id(client, "Loogika"), _cat_id(client, "Sorteerimine")
    r = client.post(
        "/api/games",
        json={"name": "Värvilised klotsid", "notes": "Rida 1\nRida 2", "age_min": 5, "age_max": 3,
              "category_ids": [sort, loogika, loogika]},
    )
    assert r.status_code == 201
    game = r.json()
    assert (game["age_min"], game["age_max"]) == (3, 5)  # swapped into order
    assert game["notes"] == "Rida 1\nRida 2"
    assert [c["name"] for c in game["categories"]] == ["Sorteerimine", "Loogika"]  # category order

    counts = {c["name"]: c["game_count"] for c in client.get("/api/categories").json()}
    assert counts["Loogika"] == 1 and counts["Töömälu"] == 0

    assert client.post("/api/games", json={"name": "X", "category_ids": [9999]}).status_code == 422
    assert client.post("/api/games", json={"name": "X", "age_min": 12}).status_code == 422


def test_filters(client):
    loogika = _cat_id(client, "Loogika")
    client.post("/api/games", json={"name": "Memo", "age_min": 4, "age_max": 6, "category_ids": [loogika]})
    client.post("/api/games", json={"name": "Pusle", "notes": "kass ja koer", "age_min": 2, "age_max": 3})
    client.post("/api/games", json={"name": "Lotto"})

    names = lambda **p: [g["name"] for g in client.get("/api/games", params=p).json()]
    assert names() == ["Lotto", "Memo", "Pusle"]
    assert names(category=loogika) == ["Memo"]
    assert names(q="koer") == ["Pusle"]
    assert names(age=5) == ["Lotto", "Memo"]
    assert names(age=2) == ["Lotto", "Pusle"]


def test_update_game_and_delete_category_keeps_game(client):
    loogika, koostoo = _cat_id(client, "Loogika"), _cat_id(client, "Koostöö")
    game = client.post("/api/games", json={"name": "Memo", "category_ids": [loogika]}).json()
    r = client.put(f"/api/games/{game['id']}", json={"name": "Memo 2", "category_ids": [koostoo, loogika]})
    assert r.status_code == 200
    assert {c["name"] for c in r.json()["categories"]} == {"Loogika", "Koostöö"}

    client.delete(f"/api/categories/{loogika}")
    game = client.get(f"/api/games/{game['id']}").json()
    assert [c["name"] for c in game["categories"]] == ["Koostöö"]


def test_image_upload_replace_and_delete(client, tmp_path):
    game = client.post("/api/games", json={"name": "Memo"}).json()
    r = client.put(f"/api/games/{game['id']}/image", files={"file": ("a.jpg", _jpeg(), "image/jpeg")})
    assert r.status_code == 200
    first = r.json()
    img = client.get(first["image_url"])
    assert img.status_code == 200
    assert max(Image.open(io.BytesIO(img.content)).size) == 1600
    assert max(Image.open(io.BytesIO(client.get(first["thumb_url"]).content)).size) == 480

    second = client.put(f"/api/games/{game['id']}/image", files={"file": ("b.jpg", _jpeg(), "image/jpeg")}).json()
    assert client.get(first["image_url"]).status_code == 404  # old file cleaned up
    assert client.get(second["image_url"]).status_code == 200

    bad = client.put(f"/api/games/{game['id']}/image", files={"file": ("x.jpg", b"not an image", "image/jpeg")})
    assert bad.status_code == 422

    assert client.delete(f"/api/games/{game['id']}").status_code == 204
    assert list((tmp_path / "images").iterdir()) == []


def test_png_with_transparency_is_converted(client):
    game = client.post("/api/games", json={"name": "Memo"}).json()
    buf = io.BytesIO()
    Image.new("RGBA", (100, 100), (255, 0, 0, 0)).save(buf, "PNG")
    r = client.put(f"/api/games/{game['id']}/image", files={"file": ("a.png", buf.getvalue(), "image/png")})
    assert r.status_code == 200
    assert r.json()["image_url"].endswith(".jpg")


def test_images_go_to_blob_when_configured(client, monkeypatch, tmp_path):
    from types import SimpleNamespace

    import vercel.blob.sync as blob

    from app import images

    store = {}
    base = "https://store.public.blob.vercel-storage.com"

    def put_blob(pathname, body, **options):
        assert options["access"] == "public"
        store[f"{base}/{pathname}"] = body
        return SimpleNamespace(url=f"{base}/{pathname}")

    def delete_blob(urls):
        for url in urls:
            store.pop(url, None)

    monkeypatch.setattr(images, "BLOB_ENABLED", True)
    monkeypatch.setattr(blob, "put_blob", put_blob)
    monkeypatch.setattr(blob, "delete_blob", delete_blob)

    game = client.post("/api/games", json={"name": "Memo"}).json()
    first = client.put(f"/api/games/{game['id']}/image", files={"file": ("a.jpg", _jpeg(), "image/jpeg")}).json()
    assert first["image_url"].startswith(base)
    assert max(Image.open(io.BytesIO(store[first["image_url"]])).size) == 1600
    assert max(Image.open(io.BytesIO(store[first["thumb_url"]])).size) == 480

    second = client.put(f"/api/games/{game['id']}/image", files={"file": ("b.jpg", _jpeg(), "image/jpeg")}).json()
    assert set(store) == {second["image_url"], second["thumb_url"]}  # old photo removed from Blob

    assert client.delete(f"/api/games/{game['id']}").status_code == 204
    assert store == {}
    assert list((tmp_path / "images").iterdir()) == []  # nothing written to local disk

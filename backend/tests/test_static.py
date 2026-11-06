import dataclasses

from fastapi.testclient import TestClient

from app.main import create_app


def _app_with_build(runtime, tmp_path):
    build = tmp_path / "dist"
    (build / "assets").mkdir(parents=True)
    (build / "index.html").write_text("<html>app</html>", encoding="utf-8")
    (build / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("nope", encoding="utf-8")
    settings = runtime.settings.model_copy(update={"static_dir": build})
    return create_app(dataclasses.replace(runtime, settings=settings), start_worker=False)


def test_serves_build_files_and_falls_back_to_index_for_app_routes(runtime, tmp_path):
    with TestClient(_app_with_build(runtime, tmp_path)) as client:
        asset = client.get("/assets/app.js")
        assert asset.text == "console.log(1)"
        assert "immutable" in asset.headers["cache-control"]

        for path in ("/", "/chat/3", "/library"):
            page = client.get(path)
            assert page.status_code == 200 and page.text == "<html>app</html>", path
            assert page.headers["cache-control"] == "no-cache"

        # Outside the build folder is never served.
        assert "nope" not in client.get("/..%2Fsecret.txt").text


def test_api_routes_win_over_the_frontend(runtime, tmp_path):
    with TestClient(_app_with_build(runtime, tmp_path)) as client:
        assert client.get("/api/jobs").json() == []
        assert client.get("/health").json()["sqlite"]["ok"] is True
        missing = client.get("/api/nope")
        assert missing.status_code == 404 and missing.json() == {"detail": "Not Found"}
        assert "openapi" in client.get("/openapi.json").json()

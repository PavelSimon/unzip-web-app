"""ZIP Extractor entrypoint."""

from fasthtml.common import serve
from unzip_app.web import app


if __name__ == "__main__":
    _ = app
    serve()

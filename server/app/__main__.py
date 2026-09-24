"""`python -m app` - run the API with settings from env/.env."""

import uvicorn

from app.core.config import Settings
from app.main import create_app

if __name__ == "__main__":
    settings = Settings()
    uvicorn.run(
        create_app(settings),
        host="127.0.0.1",
        port=settings.PORT,
        server_header=False,  # equivalent of disabling x-powered-by
        proxy_headers=settings.TRUST_PROXY,
        access_log=False,  # our CoreMiddleware writes structured access logs
    )

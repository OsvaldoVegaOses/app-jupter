import os

from app.clients import build_service_clients
from app.settings import load_settings


def main() -> int:
    settings = load_settings(os.getenv("APP_ENV_FILE"))
    clients = build_service_clients(settings)
    try:
        with clients.postgres.cursor() as cur:
            cur.execute(
                "SELECT "
                "to_regclass('public.analisis_axial'), "
                "to_regclass('public.codigos_candidatos'), "
                "to_regclass('public.analisis_codigos_abiertos'), "
                "to_regclass('public.entrevista_fragmentos')"
            )
            print(cur.fetchone())
        return 0
    finally:
        clients.close()


if __name__ == "__main__":
    raise SystemExit(main())

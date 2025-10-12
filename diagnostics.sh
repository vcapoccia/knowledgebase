bash -lc '
echo "=== ps ==="; docker compose ps;
echo; echo "=== api logs (last 80) ==="; docker compose logs --tail=80 api;
echo; echo "=== check api in-container ===";
docker compose exec -T api bash -lc "ps -ef | grep -E \"uvicorn|python\" | grep -v grep; ss -ltnp | grep 8000 || true; curl -sS http://127.0.0.1:8000/health || true"
'


#!/bin/bash
# Brain From Cero — development helper
# Usage: ./start.sh [up|down|logs|ps|build|restart|shell|ci]
set -e

CMD=${1:-up}

case "$CMD" in
  up)
    echo "Starting Brain From Cero stack..."
    docker compose up --build -d
    echo ""
    echo "Waiting for app to become healthy..."
    for i in $(seq 1 30); do
      if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        echo "API ready: http://localhost:8000"
        echo "Docs:      http://localhost:8000/docs"
        echo ""
        echo "Run './start.sh logs' to tail logs."
        exit 0
      fi
      sleep 2
    done
    echo "Timed out waiting for health check. Check logs:"
    docker compose logs app --tail=50
    exit 1
    ;;
  down)
    docker compose down
    ;;
  logs)
    docker compose logs -f "${2:-}"
    ;;
  ps)
    docker compose ps
    ;;
  build)
    docker compose build
    ;;
  restart)
    docker compose restart "${2:-}"
    ;;
  shell)
    docker compose exec app /bin/bash
    ;;
  ci)
    # Run the fast CI gate inside the app container
    docker compose exec app make ci
    ;;
  *)
    echo "Usage: $0 [up|down|logs|ps|build|restart|shell|ci]"
    exit 1
    ;;
esac

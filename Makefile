.PHONY: data db load psql clean
data:            ## generuje pełny zestaw (CSV + SQL) do ./data
	python3 generator/generate.py data
db:              ## uruchamia PostgreSQL w Dockerze
	docker compose up -d
load: data db    ## wczytuje dane do bazy (czeka na start Postgresa)
	until docker compose exec -T db pg_isready -U postgres >/dev/null 2>&1; do sleep 1; done
	docker compose exec -T db psql -U postgres -d cnc_sim -v ON_ERROR_STOP=1 < data/seed.sql
psql:
	docker compose exec db psql -U postgres -d cnc_sim
clean:
	rm -rf data
	docker compose down -v

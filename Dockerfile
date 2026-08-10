# dho_webapp.py 배포용 Dockerfile (Flask + gunicorn, NAS docker-compose에서 사용)
# DB는 PostgreSQL(postgres 서비스)이라 이미지에 안 담고 DATABASE_URL로 접속한다.
FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY dho_webapp.py pg_conn.py ./
COPY templates/ ./templates/
COPY static/ ./static/

# webapp이 항목 저장 직후 서브프로세스로 재실행하는 파생 테이블 재생성 스크립트들
# (item_backlinks/item_acquisition_*/카테고리 전용 테이블 — raw_attrs/raw_tables에서
# 파생되므로 webapp이 그 두 테이블에 쓸 때마다 다시 만들어줘야 chat도 같은 데이터를 봄)
COPY build_backlinks.py build_acquisition.py materialize_generic.py materialize_cannon.py \
     materialize_recipe.py materialize_consumable.py materialize_tarotcard.py \
     build_search_index.py ./

# build_embeddings.py는 DERIVED_PIPELINE_SCRIPTS(자동 재실행 목록)엔 없음 — 데이터가 크게
# 바뀌었을 때 `docker compose exec webapp python build_embeddings.py`로 수동 실행한다.
COPY build_embeddings.py ./

EXPOSE 5050
CMD ["gunicorn", "--bind", "0.0.0.0:5050", "--workers", "2", "dho_webapp:app"]

-- postgres 컨테이너 최초 기동(데이터 디렉토리가 비어있을 때) 1회만 자동 실행됨
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

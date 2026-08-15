-- postgres 컨테이너 최초 기동(데이터 디렉토리가 비어있을 때) 1회만 자동 실행됨
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Wiki.js 전용 DB (DHO 구조화 데이터와 스키마 분리). 이미 postgres_data 볼륨이 있는
-- 기존 배포(로컬/NAS)에서는 이 스크립트가 재실행되지 않으므로 수동으로
-- `CREATE DATABASE wikidb;`를 한 번 실행해야 한다.
CREATE DATABASE wikidb;

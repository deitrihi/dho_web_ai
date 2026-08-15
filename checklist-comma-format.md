# 숫자 콤마 텍스트 컬럼 정제 체크리스트

## 파이프라인 수정
- [x] `materialize_generic.py`: 콤마 제거 헬퍼 추가
- [x] `materialize_generic.py`: `build_category_table` 정수 판별/삽입에 콤마 제거 적용
- [x] `materialize_generic.py`: `build_relation_tables` 헤더별 숫자 판별(2-pass)로 재구성,
      숫자면 `{header}_num INTEGER`, 아니면 `{header}_text TEXT`
- [x] `materialize_cannon.py`: INT_COLUMNS 파싱 시 콤마 제거

## DB 재생성
- [x] `dho_structured.sqlite3` 백업
- [x] 7개 파생 스크립트 순서대로 재실행 (rebuild_derived_tables와 동일 순서)
- [x] 재생성 전/후 콤마 케이스 값 대조 (courtRank.명성, city__판매 아이템, cannon.penetration)
- [x] 전체 행 수 불변 확인(데이터 유실 없음) — 214개 테이블 전부 일치
- [x] cannon.penetration 절단 버그 수정 확인 (item_id 8868/8869/8912/8927/8967 전부
      원래 값(1032/1204/1050/1200/1274)으로 정상화)

## 콤마 포맷 메소드
- [x] `openwebui_tool_dho_sql.py`: `format_number()` 추가
- [x] `openwebui_tool_dho_sql.py`: `run_sql`에 적용 (식별자 컬럼 제외)
- [x] `chat/lib/dho-db.ts`: `formatNumber()` 포팅
- [x] `chat/lib/dho-db.ts`: `runSql`에 적용 (식별자 컬럼 제외)

## 검증
- [x] `run_sql`/`runSql`로 실제 조회해 콤마 포맷 확인 (Python/TS 양쪽 다 확인,
      item_id는 포맷 안 됨/penetration·명성은 "1,500" 형태로 반환됨)
- [x] webapp 기존 라우트 회귀 확인 (`/`, `/cannon`, `/cannon/8868`, `/assistant` 전부 200)
- [x] `npm run build`, `npm run lint` 통과 (chat)

## 기록
- [ ] CHANGELOG.md `[미커밋]` 항목 추가
- [ ] 옵시디언 로그(`Claude 작업 로그.md`) append
- [ ] 커밋

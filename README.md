# DHO 아카이브 로컬 크롤러

## 설치
```bash
pip install requests beautifulsoup4
```

## 사용 순서

### 1. 먼저 작은 카테고리로 테스트
실제 사이트의 HTML 구조를 제가 직접 확인하지 못했기 때문에(제 환경에서는 이 도메인에
직접 접속이 안 됩니다), 파싱 로직이 100% 맞다고 장담은 못 드려요. 전체를 돌리기 전에
건수가 적은 카테고리로 먼저 확인해보세요.

```bash
python scraper.py discover
python scraper.py crawl-lists --categories tarotCard   # 22건, 금방 끝남
python scraper.py status
```

`status` 결과에서 `tarotCard`의 "수집됨" 값이 22 근처로 나오면 정상 동작하는 것입니다.
만약 0이거나 이상하면, `dho_cache.sqlite3`의 `pages` 테이블에서 해당 페이지의 원본
HTML을 열어보고 `crawl_category_list()` / `discover_categories()`의 정규식(`re.search`
부분)을 실제 마크업에 맞게 조정해야 할 수 있습니다. (사이트가 Next.js 기반이라
서버사이드 렌더링 HTML 구조가 코드의 가정과 다를 가능성이 있어요.)

### 2. 전체 목록 크롤링 (전체 70개 카테고리, id+이름만 수집)
```bash
python scraper.py crawl-lists --all
```
이건 요청 수가 적어서 (카테고리당 페이지 수 x 1) 오래 걸리지 않습니다.

### 3. 상세 페이지 크롤링 (33,000여 건 전체 원본 HTML 캐싱)
```bash
python scraper.py crawl-details --all --delay 0.8
```
- 33,496건 × 약 0.8~1초 = 대략 7~10시간 정도 예상됩니다.
- 중간에 멈춰도(Ctrl+C, 오류 등) 다시 실행하면 이미 받은 건 건너뛰고 이어서 진행됩니다.
- 먼저 일부만 테스트하려면 `--limit 100` 옵션을 추가하세요.
- 특정 카테고리만 급하면 `--categories cannon,recipe,recipeBook` 처럼 지정 가능합니다.

### 4. 진행 상황 확인 (언제든)
```bash
python scraper.py status
```

## 결과물
`dho_cache.sqlite3` 파일 하나에 다음이 저장됩니다:
- `pages`: URL별 원본 HTML 전체 캐시
- `categories`: 카테고리 목록 및 크롤링 상태
- `items`: 카테고리별 항목 id/이름, 상세 크롤링 여부

## 다음 단계 (아직 안 만든 부분)
지금 이 스크립트는 **원본 HTML을 그대로 캐싱하는 단계**까지만 합니다.
`pages.html`에 저장된 원본을 실제 스탯/레시피/재료 테이블 등 구조화된 스키마로
파싱해서 정규화된 테이블로 옮기는 작업(2단계)은 별도로 진행하면 됩니다.

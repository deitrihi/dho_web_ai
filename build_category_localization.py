#!/usr/bin/env python3
"""
카테고리 slug -> 한글명 / 대분류 매핑을 별도 테이블(category_localization)에 저장하는 스크립트

출처
----
원본 사이트가 배포하는 정적 JS 번들 `/assets/categories-*.js` 안에 카테고리 한글명(`bt`)과
대분류 그룹 6개(`xt`: 모험/아이템/선박/인물 · 스킬/NPC/세계) 매핑이 그대로 들어있어서
그 값을 그대로 옮겨왔다 (2026-08-01, categories-BiVJAt2L.js 확인). DB 자체에는 이 정보가
없어서(dho_cache.categories.label엔 한글명은 있지만 대분류는 없음) 별도 테이블로 관리.
이 테이블은 원본 데이터를 건드리지 않고 "표시할 때만 참고하는" 로컬라이제이션 레이어다.

사용법
------
    python build_category_localization.py
"""
import sqlite3
from pathlib import Path

STRUCT_DB = Path(__file__).parent / "dho_structured.sqlite3"

# 대분류 6개: (한글 제목, 영문 flag, 그룹 내 카테고리 slug 순서)
GROUPS: list[tuple[str, str, list[str]]] = [
    ("모험", "adventure", [
        "quest", "discovery", "shipwreck", "dungeon", "treasureMap", "treasureBox",
        "legacy", "legacyTheme", "legacyClue", "treasureHuntTheme", "relic", "relicClue",
        "debateCombo", "memorialAlbum",
    ]),
    ("아이템", "item", [
        "equipment", "consumable", "tradeGoods", "recipe", "recipeBook", "transmutation",
        "furniture", "ornament", "certificate", "tarotCard", "itemEffect", "equippedEffect",
        "installationEffect", "protection", "itemShop",
    ]),
    ("선박", "ship", [
        "ship", "shipSkill", "shipMaterial", "shipBaseMaterial", "gradePerformance",
        "gradeBonus", "cannon", "studdingSail", "figurehead", "extraArmor",
        "specialEquipment", "sailorEquipment", "crest", "shipDecor",
    ]),
    ("인물 · 스킬", "person", [
        "skill", "skillRefinementEffect", "research", "major", "researchAction",
        "technic", "job", "title", "courtRank", "aide", "pet",
    ]),
    ("NPC", "npc", ["landNpc", "marineNpc", "ganador", "cityNpc", "sellerNpc"]),
    ("세계", "world", [
        "city", "region", "field", "sea", "nation", "culture", "event",
        "historicalEvent", "privateFarm", "portPermit", "liner",
    ]),
]

# slug -> 한글 카테고리명 (원본 JS 번들의 `bt` 객체)
LABELS: dict[str, str] = {
    "quest": "퀘스트", "discovery": "발견물", "shipwreck": "침몰선", "dungeon": "유적던전",
    "legacyTheme": "레거시테마", "legacy": "레거시", "treasureHuntTheme": "트레져헌트테마",
    "relic": "렐릭", "relicClue": "렐릭피스", "debateCombo": "논전콤보",
    "memorialAlbum": "메모리얼앨범", "treasureMap": "보물지도", "treasureBox": "트레져박스",
    "legacyClue": "레거시피스", "equipment": "장비품", "consumable": "소비품",
    "tradeGoods": "교역품", "certificate": "추천장", "furniture": "가구",
    "ornament": "장식품", "tarotCard": "타로카드", "recipeBook": "레시피책",
    "recipe": "레시피", "transmutation": "변성연금", "itemEffect": "아이템효과",
    "equippedEffect": "장비효과", "installationEffect": "장식품설치효과",
    "protection": "가호", "itemShop": "아이템샵", "ship": "선박", "shipSkill": "선박스킬",
    "shipMaterial": "선박재료", "shipBaseMaterial": "선박기본재질",
    "gradePerformance": "그레이드성능", "gradeBonus": "그레이드보너스", "cannon": "대포",
    "studdingSail": "보조돛", "figurehead": "선수상", "extraArmor": "추가장갑",
    "specialEquipment": "특수장비", "sailorEquipment": "선원장비", "crest": "문장",
    "shipDecor": "선박데코", "skill": "스킬", "skillRefinementEffect": "스킬연성효과",
    "research": "연구", "major": "전공", "researchAction": "연구행동", "technic": "테크닉",
    "job": "직업", "title": "호칭", "courtRank": "작위", "aide": "부관", "pet": "애완동물",
    "landNpc": "육상NPC", "marineNpc": "해상NPC", "ganador": "가나돌",
    "cityNpc": "도시인물", "sellerNpc": "판매NPC", "event": "이벤트",
    "historicalEvent": "역사적사건", "region": "지역", "field": "필드", "sea": "해역",
    "city": "도시", "nation": "국가", "culture": "문화", "privateFarm": "개인농장",
    "portPermit": "입항허가", "liner": "정기선",
}


def build() -> None:
    conn = sqlite3.connect(STRUCT_DB)
    conn.executescript(
        """
        DROP TABLE IF EXISTS category_localization;
        CREATE TABLE category_localization (
            slug TEXT PRIMARY KEY,
            label_ko TEXT NOT NULL,
            group_title_ko TEXT NOT NULL,
            group_flag TEXT NOT NULL,
            group_order INTEGER NOT NULL,
            order_in_group INTEGER NOT NULL
        );
        """
    )

    seen = set()
    for group_order, (group_title, group_flag, slugs) in enumerate(GROUPS):
        for order_in_group, slug in enumerate(slugs):
            label = LABELS.get(slug, slug)
            seen.add(slug)
            conn.execute(
                "INSERT INTO category_localization VALUES (?, ?, ?, ?, ?, ?)",
                (slug, label, group_title, group_flag, group_order, order_in_group),
            )
    conn.commit()

    # 실제 DB에 있는 카테고리와 대조 — 매핑에서 빠진 게 있으면 알려줌 (조용히 누락시키지 않기 위함)
    actual = {
        r[0] for r in conn.execute("SELECT DISTINCT category FROM items_core").fetchall()
    }
    missing_in_mapping = actual - seen
    extra_in_mapping = seen - actual
    print(f"[완료] category_localization {len(seen)}건 적재")
    if missing_in_mapping:
        print(f"[경고] DB에는 있는데 매핑에 없는 카테고리: {sorted(missing_in_mapping)}")
    if extra_in_mapping:
        print(f"[경고] 매핑엔 있는데 DB에 없는 카테고리: {sorted(extra_in_mapping)}")
    conn.close()


if __name__ == "__main__":
    build()

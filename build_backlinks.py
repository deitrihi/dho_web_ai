#!/usr/bin/env python3
"""
raw_attrs/raw_tables에 이미 있는 정방향 링크(이 항목 -> 다른 항목)를 뒤집어서
"이 항목을 참조하는 곳"(역방향 링크) 인덱스 테이블(item_backlinks)을 만드는 스크립트.

원본 사이트 상세 페이지의 "이 항목을 참조하는 곳" 섹션에 대응한다. 원본의 정확한 내부
집계 로직은 알 수 없어서, 우리가 이미 가진 데이터로 명확하게 계산 가능한 정의를 쓴다 —
"다른 항목의 raw_attrs/raw_tables 어딘가에 이 항목으로의 링크가 있으면 backlink"로 삼는다.

사용법
------
    python build_backlinks.py
"""
import json
import os
import sqlite3
from pathlib import Path

# DHO_DB_PATH로 오버라이드 가능 (dho_webapp.py/chat과 동일한 관례 — webapp이 항목 저장 후
# 이 스크립트를 서브프로세스로 재실행할 때 자신이 쓰는 DB 경로를 그대로 넘겨준다)
STRUCT_DB = Path(os.environ.get("DHO_DB_PATH", str(Path(__file__).parent / "dho_structured.sqlite3")))


def build() -> None:
    conn = sqlite3.connect(STRUCT_DB)
    conn.executescript(
        """
        DROP TABLE IF EXISTS item_backlinks;
        CREATE TABLE item_backlinks (
            target_category TEXT NOT NULL,
            target_item_id INTEGER NOT NULL,
            source_category TEXT NOT NULL,
            source_item_id INTEGER NOT NULL,
            source_label TEXT NOT NULL
        );
        """
    )

    rows_to_insert = []

    for category, item_id, label, links_json in conn.execute(
        "SELECT category, item_id, label, links_json FROM raw_attrs WHERE links_json IS NOT NULL AND links_json != '[]'"
    ):
        for link in json.loads(links_json):
            if link["category"] == category and link["item_id"] == item_id:
                continue  # 자기 자신을 가리키는 링크는 backlink로 안 침
            rows_to_insert.append(
                (link["category"], link["item_id"], category, item_id, label)
            )

    for category, item_id, label, rows_json in conn.execute(
        "SELECT category, item_id, label, rows_json FROM raw_tables"
    ):
        for row in json.loads(rows_json):
            for cell in row:
                for link in cell.get("links", []):
                    if link["category"] == category and link["item_id"] == item_id:
                        continue
                    rows_to_insert.append(
                        (link["category"], link["item_id"], category, item_id, label)
                    )

    print(f"[backlinks] 적재할 링크: {len(rows_to_insert)}건")

    # 같은 (target, source, label) 조합이 여러 번 나올 수 있음(표의 여러 행에서 같은 셀
    # 라벨로 같은 항목을 반복 링크하는 경우 등) -> 중복 제거
    dedup = sorted(set(rows_to_insert))
    print(f"[backlinks] 중복 제거 후: {len(dedup)}건")

    conn.executemany(
        "INSERT INTO item_backlinks (target_category, target_item_id, source_category, source_item_id, source_label) "
        "VALUES (?, ?, ?, ?, ?)",
        dedup,
    )
    conn.execute(
        "CREATE INDEX idx_item_backlinks_target ON item_backlinks (target_category, target_item_id)"
    )
    conn.commit()
    conn.close()
    print("[backlinks] 완료")


if __name__ == "__main__":
    build()

#!/usr/bin/env python3
"""파생 테이블 파이프라인 스크립트(build_backlinks.py 등)가 공용으로 쓰는 Postgres 접속 헬퍼"""
import os

import psycopg


def connect() -> psycopg.Connection:
    return psycopg.connect(os.environ["DATABASE_URL"])


def q(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'

# dho_webapp.py 배포용 Dockerfile (Flask + gunicorn, NAS docker-compose에서 사용)
# DB(dho_structured.sqlite3)는 이미지에 안 담고 볼륨으로 마운트한다 (docker-compose.yml 참고)
FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY dho_webapp.py ./
COPY templates/ ./templates/
COPY static/ ./static/

EXPOSE 5050
CMD ["gunicorn", "--bind", "0.0.0.0:5050", "--workers", "2", "dho_webapp:app"]

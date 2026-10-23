FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app /app/backend/app
COPY backend/fixtures /app/backend/fixtures
COPY engine /app/engine
RUN PYTHONPATH=/app/backend:/app/engine python -c "from app.reporting import make_report; from app.kertas_kerja import workbook"
RUN useradd --uid 10001 --create-home sqe && mkdir -p /app/data /data/files && chown -R sqe:sqe /app /data
USER sqe
WORKDIR /app/backend
EXPOSE 8000
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]

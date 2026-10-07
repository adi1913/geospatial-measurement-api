FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# GeoPandas/Shapely/PyProj/pyogrio ship binary wheels, so no system GDAL is needed.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Run as an unprivileged user; /data holds the database and the uploads.
RUN useradd --create-home appuser && mkdir /data && chown appuser /data
USER appuser

ENV DATABASE_URL=sqlite:////data/geospatial.db \
    UPLOAD_DIR=/data/uploads

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

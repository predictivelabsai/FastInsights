FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV FASTINSIGHTS_DB=/data/fastinsights.sqlite
ENV FASTINSIGHTS_PORT=5008
EXPOSE 5008
CMD ["sh", "-c", "python -c 'import db,seed; seed.build() if not db.db_exists() else None' && python web_app.py"]

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=Europe/Rome
WORKDIR /app
COPY webapp/api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY benessere /app/benessere
COPY webapp/api /app/webapp/api
RUN useradd --system --uid 10001 --home-dir /app benessere
USER 10001
EXPOSE 8780
CMD ["uvicorn","webapp.api.main:app","--host","0.0.0.0","--port","8780"]

FROM python:3.12-slim
 
WORKDIR /app
 
# Install dependencies first (layer cache optimization)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
 
COPY . .
 
VOLUME ["/data"]
 
EXPOSE 5000
 
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "app:app"]

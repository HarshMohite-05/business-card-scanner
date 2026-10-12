FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd --create-home appuser && mkdir -p /var/lib/bccm/data /var/lib/bccm/business_cards && chown -R appuser:appuser /app /var/lib/bccm
ENV BCCM_DATA_DIR=/var/lib/bccm/data BCCM_IMAGE_DIR=/var/lib/bccm/business_cards BCCM_TIMEZONE=Asia/Kolkata
USER appuser
EXPOSE 8501
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')"
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]

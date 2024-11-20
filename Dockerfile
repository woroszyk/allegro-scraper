FROM python:3.9-slim

# Instalacja Chrome i zależności
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# Ustawienie zmiennych środowiskowych dla Chrome
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver

WORKDIR /app

# Kopiowanie plików projektu
COPY requirements.txt .
COPY . .

# Instalacja zależności Pythona
RUN pip install --no-cache-dir -r requirements.txt

# Expose port
EXPOSE 8080

# Uruchomienie aplikacji
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "app:app"]

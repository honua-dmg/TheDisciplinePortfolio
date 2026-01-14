FROM python:3.9-slim

WORKDIR /app

# Install dependencies first (better caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY . .

# Streamlit config
RUN mkdir -p ~/.streamlit && \
    echo "\
[server]\n\
headless = true\n\
enableCORS = false\n\
enableXsrfProtection = false\n\
" > ~/.streamlit/config.toml

EXPOSE 8501

VOLUME /app/data

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
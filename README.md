# Document Management API

A FastAPI application with Supabase backend for document management and chat system.

## Setup

1. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up your environment variables:
- Copy `.env.example` to `.env`
- Update the values in `.env` with your Supabase credentials and other configurations

4. Run the application:
```bash
uvicorn main:app --reload
```

The API will be available at `http://localhost:8000`

## API Documentation

Once the application is running, you can access:
- Interactive API documentation (Swagger UI): `http://localhost:8000/docs`
- Alternative API documentation (ReDoc): `http://localhost:8000/redoc`

## Project Structure

```
.
├── app/
│   ├── api/
│   │   └── api_v1/
│   │       ├── api.py
│   │       └── endpoints/
│   │           └── organizations.py
│   ├── core/
│   │   └── config.py
│   ├── db/
│   │   └── supabase.py
│   └── schemas/
│       └── base.py
├── .env
├── .env.example
├── main.py
├── requirements.txt
└── README.md
```

## Docker file advice

FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

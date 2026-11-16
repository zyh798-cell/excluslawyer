FROM python:3.11-slim

WORKDIR /app

# INSTALL_ML=false 时只装轻量依赖（演示/测试模式）
ARG INSTALL_ML=true

COPY requirements.txt requirements-ml.txt ./
RUN pip install --no-cache-dir -r requirements.txt && \
    if [ "$INSTALL_ML" = "true" ]; then pip install --no-cache-dir -r requirements-ml.txt; fi

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

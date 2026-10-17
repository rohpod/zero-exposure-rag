FROM python:3.12-slim

WORKDIR /app

# System build deps needed for llama-cpp-python's CMake build on s390x.
# See docs/environment.md for the march=z16 fix this mirrors.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
ENV CMAKE_ARGS="-DGGML_NATIVE=OFF -DCMAKE_C_FLAGS=-march=z16 -DCMAKE_CXX_FLAGS=-march=z16"
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

# Model weights and local secrets are not baked into the image.
# Mount them at runtime:
#   -v $(pwd)/models:/app/models
#   -v $(pwd)/app/auth_tokens.local.json:/app/app/auth_tokens.local.json
# See docs/environment.md for how to obtain the model file.

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

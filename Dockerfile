FROM python:3.11-slim

# opencv-python-headless still needs a couple of shared libraries present
# on a minimal Debian base image (no GUI/X11 stack required since we use
# the "headless" build).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libglib2.0-0 \
        libgl1 \
        iputils-ping \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN pip install --no-cache-dir -e .

ENTRYPOINT ["python", "-m", "camtoolkit"]
CMD ["--help"]

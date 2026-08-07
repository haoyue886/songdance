FROM python:3.11.12-slim-bookworm

ENV PIP_DEFAULT_TIMEOUT=600 \
    PIP_RETRIES=10

RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu \
        torch==2.4.1 torchaudio==2.4.1

COPY requirements.txt fetch_pinned_source.py /tmp/
RUN python /tmp/fetch_pinned_source.py /tmp/aria-amt \
    && pip install --no-cache-dir --no-deps /tmp/aria-amt \
    && pip install --no-cache-dir -r /tmp/requirements.txt
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /work
ENTRYPOINT ["aria-amt"]

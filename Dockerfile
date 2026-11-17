ARG BASE_IMAGE=python:3.12-slim
FROM ${BASE_IMAGE}
WORKDIR /app
COPY cpu-a-guide-20261110-v1/baselines/requirements.txt /tmp/requirements.txt
RUN python -m pip install --no-cache-dir -r /tmp/requirements.txt
COPY contest_rounds.py run_all.py container_entry.py ./
COPY cpu-a-guide-20261110-v1/ ./cpu-a-guide-20261110-v1/
COPY cpu-b-rul-20261110-v1/ ./cpu-b-rul-20261110-v1/
COPY cpu-c-guide-20261110-v1/ ./cpu-c-guide-20261110-v1/
ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "container_entry.py"]
CMD ["--output", "/results", "--rounds", "10"]

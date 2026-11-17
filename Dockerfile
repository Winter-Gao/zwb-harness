FROM smart-training-harness:competition-v3
WORKDIR /app
ADD sdk.tar.gz /opt/
# Install the pure-Python SDK directly into the base interpreter's package directory.
RUN python3 -c "import sysconfig,shutil; shutil.copytree('/opt/contest-harness-sdk-1.0.2/contest_harness', sysconfig.get_path('purelib')+'/contest_harness')" && cp /opt/contest-harness-sdk-1.0.2/template/harness.py /app/harness.py
COPY contest_submission.py /app/contest_submission.py
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
ENTRYPOINT ["python3", "/app/harness.py"]

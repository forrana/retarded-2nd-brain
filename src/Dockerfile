FROM python:3.14-alpine

WORKDIR /app
COPY processor.py .
RUN pip install watchdog pyyaml requests
CMD ["python", "processor.py"]

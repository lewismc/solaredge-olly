FROM python:3.12-slim

# Run as a non-root user. The named volume at /var/lib/geolocate inherits this
# ownership on first mount, so the location cache is writable.
RUN useradd --system --uid 10001 --home-dir /var/lib/geolocate geolocate \
 && mkdir -p /var/lib/geolocate \
 && chown geolocate:geolocate /var/lib/geolocate

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py .

USER geolocate
EXPOSE 9110
CMD ["python", "-u", "server.py"]

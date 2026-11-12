# Exceptional exercise image, not the normal Dockerfile or release artifact.
ARG KNOWN_GOOD_IMAGE
FROM ${KNOWN_GOOD_IMAGE}
COPY game_day_fault.py /app/game_day_fault.py
CMD ["sh", "-c", "exec uvicorn game_day_fault:app --host 0.0.0.0 --port \"${PORT}\" --workers 1 --no-access-log"]

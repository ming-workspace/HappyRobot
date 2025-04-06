FROM ubuntu:latest
LABEL authors="ming"

WORKDIR /app
COPY . .
RUN pip install python-dotenv
EXPOSE 8000
CMD ["python", "load_service.py"]
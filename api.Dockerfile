# Use the official Python image as the base image
FROM python:3.11-slim-bookworm@sha256:94a8fee35252d06ab75856f15f12c7bae67b10e8a6da93c7fded82b2610926cd
# Links the image to this repository when it is pushed to ghcr.io (it then inherits the repository's access)
LABEL org.opencontainers.image.source=https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System

# Set environment variables

# Upgrade pip
RUN python3 -m pip install --upgrade pip

ENV TZ=Asia/Kolkata
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone
RUN apt update -y && apt install ffmpeg libsm6 libxext6  -y

# Copy the project contents - src/ folder to docker image
WORKDIR /Multi-Person-Face-Recognition
COPY src/ src/

# Install requirements
RUN python3 -m pip install -r src/api/requirements.txt

# Expose the port your FastAPI app will run on
EXPOSE 8000

# Start the FastAPI application
CMD ["python3", "src/api/app.py"]

# Use an official Python runtime as a parent image
FROM python:3.14-slim-trixie@sha256:cd89c30eda26ee911a4611b18680086e0ea42e6f5f8cbe653d07fa7958c9cec8
# Links the image to this repository when it is pushed to ghcr.io (it then inherits the repository's access)
LABEL org.opencontainers.image.source=https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System

# Set environment variables

# Upgrade pip
RUN python3 -m pip install --upgrade pip

ENV TZ=Asia/Kolkata
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Set the working directory in the container
WORKDIR /Multi-Person-Face-Recognition

RUN apt update && apt install ffmpeg libxext6 libsm6 -y
# Copy the requirements file into the container at /app
COPY src/automatic-vector-db-updation/requirements.txt src/automatic-vector-db-updation/requirements.txt

# Install any needed packages specified in requirements.txt
RUN python3 -m pip install -r src/automatic-vector-db-updation/requirements.txt

# Copy project source
COPY src/ src/

# Give starting point of project
 CMD ["python3", "src/automatic-vector-db-updation/milvus_updater.py"]

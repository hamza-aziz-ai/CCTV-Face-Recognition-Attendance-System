# Use an official Python runtime as a parent image
FROM python:3.11-slim-bookworm@sha256:94a8fee35252d06ab75856f15f12c7bae67b10e8a6da93c7fded82b2610926cd

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

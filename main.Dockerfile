# syntax=docker/dockerfile:1
  
# Step 1 - Select base docker image
FROM python:3.11-slim-bookworm@sha256:94a8fee35252d06ab75856f15f12c7bae67b10e8a6da93c7fded82b2610926cd
# Links the image to this repository when it is pushed to ghcr.io (it then inherits the repository's access)
LABEL org.opencontainers.image.source=https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System

# Set environment variables
ENV CAM_PORT=554
ENV STREAM_ENDPOINT=stream1

# Step 2 - Upgrade pip
RUN pip3 install --upgrade pip --no-cache-dir

# Step 3 - Set timezone, for updating system in subsequent steps
#https://grigorkh.medium.com/fix-tzdata-hangs-docker-image-build-cdb52cc3360d
ENV TZ=Asia/Kolkata
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Step 4 - Change work directory in docker image
WORKDIR /Multi-Person-Face-Recognition

# Step 5 - Install additional libraries to work on videos
RUN apt update -y && apt install ffmpeg libsm6 libxext6  -y

# Step 6 - Copy and install project requirements
COPY requirements.txt requirements.txt
RUN pip3 install -r requirements.txt

# Step 7 - Copy project source
COPY src/ src/

# Step 8 - Give starting point of project
CMD ["python3", "src/main.py"]
# For just starting the container (i.e., we will have to manually execute the program from inside the container), uncomment next line
#CMD ["sh"]

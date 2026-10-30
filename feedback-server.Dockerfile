# syntax=docker/dockerfile:1

# Step 1 - Select base docker image
FROM python:3.14-slim-trixie@sha256:cd89c30eda26ee911a4611b18680086e0ea42e6f5f8cbe653d07fa7958c9cec8
# Links the image to this repository when it is pushed to ghcr.io (it then inherits the repository's access)
LABEL org.opencontainers.image.source=https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System

# Step 2 - Upgrade pip
RUN python3 -m pip install --upgrade pip --no-cache-dir

ENV TZ=Asia/Kolkata
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone
RUN apt update -y && apt install ffmpeg libsm6 libxext6  -y

# Step 2 - Copy the project contents - src/ folder to docker image
WORKDIR /Multi-Person-Face-Recognition
COPY src/feedback_server/requirements.txt src/feedback_server/requirements.txt

# Step 3 - Install project requirements
RUN python3 -m pip install -r src/feedback_server/requirements.txt

# Step 4 - Copy project source
COPY src/ src/

# Step 5 - Give starting point of project
CMD ["python3", "src/feedback_server/feedback_msg_server_controller.py"]

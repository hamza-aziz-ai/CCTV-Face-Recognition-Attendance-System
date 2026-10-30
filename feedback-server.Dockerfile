# syntax=docker/dockerfile:1

# Step 1 - Select base docker image
FROM python:3.11-slim-bookworm@sha256:94a8fee35252d06ab75856f15f12c7bae67b10e8a6da93c7fded82b2610926cd

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

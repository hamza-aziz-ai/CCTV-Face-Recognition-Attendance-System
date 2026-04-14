# syntax=docker/dockerfile:1
  
# Step 1 - Select base docker image
FROM python:3.8-slim-buster

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

# Step 7 - Uncomment following line if we want to copy project contents to docker image
#COPY . .

# Step 8 - Give starting point of project
CMD ["python3", "src/main.py"]
# For just starting the container (i.e., we will have to manually execute the program from inside the container), uncomment next line
#CMD ["sh"]

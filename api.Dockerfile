# Use the official Python image as the base image
FROM python:3.8-slim-buster

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
EXPOSE 9090

# Start the FastAPI application
CMD ["python3", "src/api/app.py"]

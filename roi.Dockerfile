# Use the official Python image as the base image
FROM python:3.14-slim-trixie@sha256:cd89c30eda26ee911a4611b18680086e0ea42e6f5f8cbe653d07fa7958c9cec8
# Links the image to this repository when it is pushed to ghcr.io (it then inherits the repository's access)
LABEL org.opencontainers.image.source=https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System

# Upgrade pip
RUN python3 -m pip install --upgrade pip --no-cache-dir

ENV TZ=Asia/Kolkata
# OpenCV's warnings can quote a camera URL with its password (a % in it reads as an image-sequence pattern); our own logs report camera failures
ENV OPENCV_LOG_LEVEL=ERROR
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Install ffmpeg, libsm6, libxext6
RUN apt update && apt upgrade -y
RUN apt install -y ffmpeg libsm6 libxext6

# Set the working directory to /Multi-Person-Face-Recognition
WORKDIR /Multi-Person-Face-Recognition

# Copy the current directory contents into the container at /Multi-Person-Face-Recognition
COPY Custom-ROI-Provisioning/ Custom-ROI-Provisioning/
# The page reuses src/parameters.py and src/util; it writes only the mounted camera configuration
COPY src/ src/

# Install requirements
RUN python3 -m pip install -r Custom-ROI-Provisioning/requirements.txt

# Expose the port your Flask app will run on
EXPOSE 8069

# Start the Flask application
CMD ["python3", "-m", "flask", "--app", "Custom-ROI-Provisioning/app.py", "run", "--host=0.0.0.0", "--port=8069"]

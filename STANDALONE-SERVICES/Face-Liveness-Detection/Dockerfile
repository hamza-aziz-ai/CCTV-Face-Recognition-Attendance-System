# Use the NVIDIA CUDA base image with PyTorch support
FROM nvcr.io/nvidia/pytorch:22.11-py3

# Upgrade pip
RUN python3 -m pip install --upgrade pip

ENV TZ=Asia/Kolkata
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Set the working directory
WORKDIR /Face-Liveness-Detection

RUN apt update && apt install ffmpeg libsm6 libxext6 netcat -y

# Copy the local directory contents to the container
COPY requirements.txt requirements.txt

# Install any necessary dependencies
RUN pip install --no-cache-dir -Ir requirements.txt

# Define the command to run the application
CMD ["python3", "api.py"]

# Use the official Python image as the base image
FROM python:3.8-slim-buster

# Upgrade pip
RUN python3 -m pip install --upgrade pip --no-cache-dir

ENV TZ=Asia/Kolkata
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Install ffmpeg, libsm6, libxext6
RUN apt update && apt upgrade -y
RUN apt install -y ffmpeg libsm6 libxext6

# Set the working directory to /Multi-Person-Face-Recognition
WORKDIR /Multi-Person-Face-Recognition

# Copy the current directory contents into the container at /Multi-Person-Face-Recognition
COPY Custom-ROI-Provisioning/ Custom-ROI-Provisioning/
Copy src/ src/

# Change permissions for parameters.py
RUN chmod 777 src/parameters.py

# Install requirements
RUN python3 -m pip install -r Custom-ROI-Provisioning/requirements.txt

# Expose the port your Flask app will run on
EXPOSE 8069

# Start the FastAPI application
CMD ["python3", "-m", "flask", "--app", "Custom-ROI-Provisioning/app.py", "run", "--host=0.0.0.0", "--port=8069"]

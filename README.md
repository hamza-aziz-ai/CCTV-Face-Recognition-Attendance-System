# Multi-Person-Face-Recognition

## Secrets and Configuration

Secrets are not stored in this repository. Copy `.env.example` to `.env` in the project root and fill in the values; `docker-compose` reads it automatically.

Camera configuration (camera IPs, credentials and ERP endpoints) is also kept out of git. Copy `src/Camera-Configuration/<INSTITUTE>/camera_configuration.example.json` to `camera_configuration.json` in the same folder and fill in the real values. A camera whose `username` or `password` is `null` falls back to `CAM_USERNAME` / `CAM_PASSWORD` from `.env`.

## How to Start the Project?

The following steps will help you to start the project:

### Clone the Project

```bash
# Clone repository from GitHub
git clone git@github.com:anubhavpatrick/Multi-Person-Face-Recognition.git CCTV-Face-Recognition-Attendance-System

# Make every bash script inside the repository executable
find CCTV-Face-Recognition-Attendance-System -type f -name "*.sh" -exec chmod +x {} \;

# Change directory to the project
cd CCTV-Face-Recognition-Attendance-System
```

### Version Control Dataset Collection

We can contribute in dataset collection using DVC.

1. First we need to DVC in our systems
   - Install DVC in local system
   ```bash
   # We can install DVC in our local systems from repository
   
   sudo wget \
       https://dvc.org/deb/dvc.list \
       -O /etc/apt/sources.list.d/dvc.list
   
   wget -qO - https://dvc.org/deb/iterative.asc | gpg --dearmor > packages.iterative.gpg
   
   sudo install -o root -g root -m 644 packages.iterative.gpg /etc/apt/trusted.gpg.d/
   
   rm -f packages.iterative.gpg
   
   sudo apt update
   
   sudo apt install dvc
   ```
   - Install DVC on DGX
   ```bash
   # Since we can not install DVC directly from repository on DGX, we will install it using pip
   
   python3 -m venv .venv
   source .venv/bin/activate
   
   python3 -m pip install --upgrade pip
   python3 -m pip install "dvc[all]"
   ```
   
2. Authenticate Google API
   - Since we can not authenticate Google API on remote server using Google Cloud, we need to authenticate on local system itself. Later, we can `scp` the generated credentials to the remote server (DGX).
     ```bash
     dvc remote modify --local face-recognition-dataset-gdrive gdrive_user_credentials_file ~/.gdrive/user-credentials.json
     
     # This command will ask you to authenticate. Follow the steps to authenticate.
     dvc fetch
     ```
3. SCP Generated Credentials on DGX
   ```bash
   # Replace variables with their actual values
   scp -r ${HOME}/.gdrive ${USER}@${IP_ADDRESS}:${HOME}
   ```

4. Adding and Pushing `FACIAL-RECOGNITION-DATASET` to DVC
   ```bash
   # Add the FACIAL-RECOGNITION-DATASET to DVC, this will create a FACIAL-RECOGNITION-DATASET.dvc file
   dvc add FACIAL-RECOGNITION-DATASET
   
   # Commit changes in the .dvc file
   dvc commit FACIAL-RECOGNITION-DATASET.dvc
   git add FACIAL-RECOGNITION-DATASET.dvc .gitignore
   git commit -m "Modified FACIAL-RECOGNITION-DATASET.dvc and .gitignore"
   # Push the modified files to the specific branch. Replace <branch-name> with actual branch name
   git push -u origin <branch-name>
   
   # Push the FACIAL-RECOGNITION-DATASET to the specified origin
   dvc push FACIAL-RECOGNITION-DATASET.dvc --remote face-recognition-dataset-gdrive
   ```

5. Fetching and Pulling `FACIAL-RECOGNITION-DATASET` from DVC Remote (in our case Google Drive)
   ```bash
   # Fetch from GitHub
   git fetch
   
   # Switch and pull the specified branch
   git checkout <branch-name>
   git pull origin <branch-name>
   
   # Fetch and pull FACIAL-RECOGNITION-DATASET from DVC
   dvc fetch
   dvc pull FACIAL-RECOGNITION-DATASET.dvc
   ```

*You can learn more about DVC from here [https://dvc.org/doc/start](https://dvc.org/doc/start)*

### Changing Parameters and Camera's Region of Interest (ROI)

- If you want change the parameters and camera's region of interest (ROI) for the project, you can do this by editing the file under the location [`src/parameters.py`](src/parameters.py)

- If you want to change the ports exposed to the docker containers, you can do this by editing the `ports` defined in [`docker-compose-main.yml`](docker-compose-main.yml)

### Starting the Project

You can start the project in the following two ways:

1. Start complete project in one go using bash script. You can do this by executing the following command in your terminal.

   ```bash
   # Start complete project in one go using bash script
   ./start_complete_project.sh
   ```

2. Start the project in two steps:

    - First by starting the standalone core modules of the project (*InsightFace-REST*, *Milvus Vector Database*, *Face Liveness Detection* and *Confluent Kafka*).

      ```bash
      # Start standalone modules
      ./start_standalone_services.sh
      ```

    - Then, start the main project using *docker-compose*.

      ```bash
      # Start main project using docker-compose
      docker-compose -f docker-compose-main.yml up -d
      ```

## How to Stop the Project?

If you wish to stop the project, you can do it in the following two ways:

1. Stop the complete project in one go using bash script. You can do this by executing the following command in your terminal.

   ```bash
   # Start complete project in one go using bash script
   ./stop_complete_project.sh
   ```

2. Stop the project in two steps:
    - First, by stopping the main project using *docker-compose*.

      ```bash
      # Stop main project using docker-compose
      docker-compose -f docker-compose-main.yml down
      ```

    - Then, stopping the standalone core modules of the project (*InsightFace-REST*, *Milvus Vector Database*, *Face Liveness Detection* and *Confluent Kafka*).

      ```bash
      # Stop the standalone modules
      ./stop_standalone_services.sh
      ```

## Ports and GPU Information for the Project Containers

| Service                       | Image Name                                                  | Container Name                                       | Port Mapping | GPU (if utilizing) |
|-------------------------------|-------------------------------------------------------------|------------------------------------------------------|--------------|--------------------|
| InsightFace-REST API          | insightface-rest:v0.9.0.0                                   | insightface-rest-gpu-mig-trt-0                       | 19000:18080  | 7:0 (10 GB)        |
|                               |                                                             | insightface-rest-gpu-mig-trt-1                       | 19001:18080  | 7:1 (10 GB)        |
| Milvus Vector Database        | minio/minio:RELEASE.2023-03-20T20-16-18Z                    | milvus-minio                                         | 9001:9001    |                    |
|                               |                                                             |                                                      | 9000:9000    |                    |
|                               | milvusdb/milvus:v2.5.1-gpu                                  | milvus-standalone                                    | 19530:19530  | 7:4 (5 GB)         |
|                               |                                                             |                                                      | 9091:9091    |                    |
|                               | quay.io/coreos/etcd:v3.5.14                                 | milvus-etcd                                          |              |                    |
| Confluent Kafka               | confluentinc/cp-kafka:7.8.0                                 | broker                                               | 9092:9092    |                    |
|                               |                                                             |                                                      | 9101:9101    |                    |
|                               | cnfldemos/cp-server-connect-datagen:0.6.4-7.6.0             | connect                                              | 8083:8083    |                    |
|                               | confluentinc/cp-enterprise-control-center:7.8.0             | control-center                                       | 9021:9021    |                    |
|                               | confluentinc/ksqldb-examples:7.8.0                          | ksql-datagen                                         |              |                    |
|                               | confluentinc/cp-ksqldb-cli:7.8.0                            | ksqldb-cli                                           |              |                    |
|                               | confluentinc/cp-ksqldb-server:7.8.0                         | ksqldb-server                                        | 8088:8088    |                    |
|                               | confluentinc/cp-kafka-rest:7.8.0                            | rest-proxy                                           | 8082:8082    |                    |
|                               | confluentinc/cp-schema-registry:7.8.0                       | schema-registry                                      | 8081:8081    |                    |
| Nginx Load Balancer           | nginx                                                       | docker-nginx-insightface                             | 6385:18080   |                    |
|                               |                                                             | docker-nginx-face-liveness-detection                 | 6386:6969    |                    |
| CCTV Stream Producer-Consumer | cctv-face-recognition-producer-consumer:v-beta              | cctv-face-recognition-producer-consumer              |              |                    |
| PostgreSQL Database           | postgres:12-bullseye                                        | cctv-face-recognition-postgresql-database            | 5432:5432    |                    |
| Database Controller           | cctv-face-recognition-database-controller:v-beta            | cctv-face-recognition-database-controller            | 20001:20001  |                    |
| Kafka Message Controller      | cctv-face-recognition-feedback-controller:v-beta            | cctv-face-recognition-feedback-controller            | 20012:20012  |                    |
| API for JSON Result           | cctv-face-recognition-api:v-beta                            | cctv-face-recognition-api                            | 9090:8000    |                    |
| Face Liveness Detection       | face-liveness-detection:v-beta                              | face-liveness-detection-container-2                  | 6970:6969    | 7:2 (5 GB)         |
|                               |                                                             | face-liveness-detection-container-2                  | 6971:6969    | 7:3 (5 GB)         |
| Display Face on Raspberry Pi  | cctv-face-recognition-front-face-image-display:v-beta       | cctv-face-recognition-front-face-image-display       | 20013:20013  |                    |
| Dynamic Facial Data Collector | cctv-face-recognition-dynamic-face-dataset-collector:v-beta | cctv-face-recognition-dynamic-face-dataset-collector | 8000:8000    |                    |
| Automatic VectorDB Update     | cctv-face-recognition-automate-milvus-update:v-beta         | cctv-face-recognition-automate-milvus-update         |              |                    |


## Camera Information

Currently, we have installed 20 CCTV Cameras at ABESIT Main Gate. The camera configuration file is located at [src/Camera-Configuration/ABESIT/camera_configuration.json](src/Camera-Configuration/ABESIT/camera_configuration.json)
For GLBITM, look for [src/Camera-Configuration/GLBITM/camera_configuration.json](src/Camera-Configuration/GLBITM/camera_configuration.json)

## Raspberry Pi Configuration

For first time configuration, please follow [First-Time-Raspberry-Setup.md](Kafka-WebApp/README.md)

If you want to change the parameters for an already set up Raspberry Pi, you can follow [Configure-Parameters-for-Raspberry.md](Kafka-WebApp/Configure-Parameters-for-Raspberry.md)

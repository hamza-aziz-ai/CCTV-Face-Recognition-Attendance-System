# face_liveness_detection.py
import os
import sys
from collections import Counter
import numpy as np
import torch
# import time
# Adjust the import paths according to your project structure
from src.anti_spoof_predict import AntiSpoofPredict
# from custom_logging import multicam_server_logger

# Initialize the anti-spoofing model
face_anti_spoofing_model = AntiSpoofPredict(0, "resources/anti_spoof_models/4_0_0_80x80_MiniFASNetV1SE.pth")  # Device ID 0 for GPU or -1 for CPU


def face_liveness_detection(person_id: str, face_array_list: list) -> dict:
    try:
        real_faces_list = []
            
        # Convert face_array_list to a tensor batch
        batch = torch.stack([torch.tensor(face_array, dtype=torch.float32).permute(2, 0, 1) for face_array in face_array_list]).to(face_anti_spoofing_model.device)
        # tick = time.time()
        prediction = face_anti_spoofing_model.predict(batch)
        # tock = time.time()
        # total_time = tock - tick
        labels = np.argmax(prediction, axis=1)
        # print(label)

        for label in labels:
            if label == 1:
                real_faces_list.append("Real Face")
            else:
                real_faces_list.append("Spoof Face")

        # multicam_server_logger.info(f"Time taken to predict liveness on batch of faces of size {len(face_array_list)} = {round((total_time * 1000), 2)} milliseconds")

        return {person_id: Counter(real_faces_list)}

    except Exception as e:
        return {"error": str(e)}

"""
This module is a server that performs face recognition (using the face_recognition library)
on multiple video streams

Reference for Multi-Processing Locking:
https://stackoverflow.com/questions/57095895/how-to-use-multiprocessing-queue-with-lock

Author: Anubhav Patrick and Hamza Aziz
Date: 2022-03-17
"""
import json
import threading
import time
from collections import Counter, defaultdict
import urllib.parse
import cv2
import numpy as np

from custom_logging import multicam_server_logger
from feedback_server.feedback_message_kafka_publisher import create_kafka_producer
# Custom modules
from parameters import FRAME_HEIGHT, \
    FRAME_WIDTH, \
    FRAME_SIZE, \
    BATCH_SIZE, \
    CROP_ROI, \
    IP_CAM_REINIT_WAIT_DURATION, \
    FRAME_RATE_FACTOR, \
    DARKNESS_DETECTION, \
    LOW_LIGHT_INTENSITY_DETECTION_BUFFER_SIZE, \
    MAXIMUM_DARK_FRAMES, \
    RESIZE_FRAME, \
    CAM_USERNAME, \
    CAM_PASSWORD, \
    CAM_PORT, \
    STREAM_ENDPOINT, \
    CAMERA_CONFIGURATION_FILE
from util.generic_utilities import map_camera_to_kafka_topic_and_partition, resize_roi_to_area, crop_and_mask_roi

# A list of all the active cameras
cameras = []
camera_to_topic_and_partition = map_camera_to_kafka_topic_and_partition()


# class FrameStatsManager:
#     def __init__(self, batch_size):
#         self.batch_size = batch_size
#         self.total_collected = 0
#         self.start_time = None
#         self.lock = threading.Lock()
#         self.per_camera_stats = defaultdict(lambda: {"read": 0, "put": 0, "discarded": 0})
#
#     def record_read(self, cam_name):
#         with self.lock:
#             self.per_camera_stats[cam_name]["read"] += 1
#
#     def record_put(self, cam_name):
#         with self.lock:
#             if self.total_collected == 0:
#                 self.start_time = time.perf_counter()
#             self.total_collected += 1
#             self.per_camera_stats[cam_name]["put"] += 1
#
#             if self.total_collected >= self.batch_size:
#                 end_time = time.perf_counter()
#                 elapsed = end_time - self.start_time
#                 self.report(elapsed)
#                 self.reset()
#
#     def record_discarded(self, cam_name):
#         with self.lock:
#             self.per_camera_stats[cam_name]["discarded"] += 1
#
#     def reset(self):
#         self.total_collected = 0
#         self.start_time = None
#         self.per_camera_stats = defaultdict(lambda: {"read": 0, "put": 0, "discarded": 0})
#
#     def report(self, elapsed):
#         multicam_server_logger.debug(f"[PRODUCER] [FRAME STATS REPORT] Collected {self.batch_size} frames in {elapsed:.6f} seconds")
#         for cam, stats in self.per_camera_stats.items():
#             multicam_server_logger.debug(
#                 f"  -> {cam}: Read={stats['read']}, Put={stats['put']}, Discarded={stats['discarded']}"
#             )
#
# frame_stats_manager = FrameStatsManager(BATCH_SIZE)


class IPCamera:
    """A class to represent an IP camera"""

    def __init__(self, cam_name, camera_config: dict , shared_buffer):
        global camera_to_topic_and_partition

        """Initialize the camera"""
        self.frame = None
        self.shared_buffer = shared_buffer
        self.cam_name = cam_name
        self.cam_ip = camera_config["ip_address"]
        self.cam_port = CAM_PORT if camera_config["port"] is None else camera_config["port"]
        self.username = CAM_USERNAME if camera_config["username"] is None else camera_config["username"]
        self.password = CAM_PASSWORD if camera_config["password"] is None else urllib.parse.quote(camera_config["password"])
        self.stream_endpoint = STREAM_ENDPOINT if camera_config["endpoint"] is None else camera_config["endpoint"]
        self.roi = camera_config["masking-coordinates"]
        # Map camera to its corresponding kafka topic and partition
        self.kafka_topic_name, self.topic_partition = camera_to_topic_and_partition[self.cam_name]
        # Create Kafka Producer
        self.producer = create_kafka_producer()
        # initialize the video camera stream and read the first frame
        self.stream = cv2.VideoCapture(self.cam_ip if self.cam_ip.startswith("http") else f"rtsp://{self.username}:{self.password}@{self.cam_ip}:{self.cam_port}/{self.stream_endpoint}")
        # self.stream = cv2.VideoCapture(f"http://{self.cam_ip}:4747/video")
        # we need to read the first frame to initialize the stream
        # _, _ = self.stream.read()
        self.grabbed, _ = self.stream.read()
        # store whether the camera stream was initialized successfully
        self.is_initialized = self.grabbed
        # set the flag to process the frame
        self.process_this_frame = True
        # initialize a frame counter
        self.frame_counter = 0
        # buffers for darkness detection
        self.light_intensity_detection_buffer = []
        self.darkness_buffer = []
        # initial darkness status
        self.too_dark = False
        # Flag to track if adequate lighting message is sent
        self.adequate_lighting_message_sent = True
        # Flag to track if inadequate lighting message is logged
        self.inadequate_lighting_message_logged = False

        if not self.is_initialized:
            multicam_server_logger.error(
                f"Camera stream from {self.cam_name} (url: {self.cam_ip})) unable to initialize"
            )
            # self.send_kafka_message(f"ERROR: Camera stream from {self.cam_name} (url: {self.cam_ip})) unable to initialize")
        else:
            multicam_server_logger.info(
                f"Camera stream from {self.cam_name} (url: {self.cam_ip}) initialized"
            )
            # self.send_kafka_message(f"SUCCESS: Camera stream from {self.cam_name} (url: {self.cam_ip})) initialized")

    def _read_one_frame(self):
        """Reads a frame from the camera"""
        self.grabbed, self.frame = self.stream.read()

    def _read_and_discard_frame(self):
        """Reads and discards one frame"""
        _, _ = self.stream.read()

    def release(self):
        """Releases the camera stream"""
        self.stream.release()

    @staticmethod
    def is_too_dark(frame, adaptive=True, threshold=80):
        # Convert frame to grayscale
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        if adaptive:
            # Use adaptive thresholding to determine darkness
            mean_intensity = cv2.mean(gray)[0]
            return mean_intensity < threshold
        else:
            # Calculate the average pixel intensity
            avg_intensity = np.mean(gray)
            # Check if the average intensity is below the threshold
            return avg_intensity < threshold

    @staticmethod
    def reduce_noise(frame):
        # Apply Gaussian blur to reduce noise
        return cv2.GaussianBlur(frame, (5, 5), 0)

    def place_frame_in_buffer(self):
        """Places the frame in the buffer"""
        # frame_processed = None
        if self.process_this_frame:
            self._read_one_frame()
            # frame_stats_manager.record_read(self.cam_name)

            if not self.grabbed:
                # if the frame was not grabbed, then we have reached the end of the stream
                multicam_server_logger.error(
                    f'Could not read a frame from the camera stream from {self.cam_name} (url: {self.cam_ip})). '
                    f'Releasing the stream...')
                self.release()
                self.is_initialized = False
                # frame_stats_manager.record_discarded(self.cam_name)
            else:
                # Create a copy of the original frame
                frame_copy = self.frame.copy()
                # rgb_frame = cv2.cvtColor(self.frame, cv2.COLOR_BGR2RGB)

                # print(self.roi)
                if CROP_ROI and self.roi is not None:
                    # Separate Region of Interest from the frame
                    roi_frame = crop_and_mask_roi(self.frame, self.roi)
                    self.frame = resize_roi_to_area(roi_frame)
                elif RESIZE_FRAME:
                    if self.frame.shape[0] > FRAME_HEIGHT or self.frame.shape[1] > FRAME_WIDTH:
                        self.frame = cv2.resize(self.frame, (FRAME_WIDTH, FRAME_HEIGHT), interpolation=cv2.INTER_AREA)

                if DARKNESS_DETECTION:
                    # Reduce noise from the frame
                    frame_copy = self.reduce_noise(frame_copy)

                    # Put the frame_copy in `light_intensity_detection_buffer`
                    self.light_intensity_detection_buffer.append(frame_copy)

                    # Check if the extracted roi is too dark for processing
                    if self.is_too_dark(frame_copy, adaptive=True):
                        self.darkness_buffer.append(True)
                    else:
                        self.darkness_buffer.append(False)

                    # print()
                    # print("=======================================================================================")
                    # print(f"1) Darkness Status: {self.too_dark}")
                    # Make decision whether it is getting dark or not
                    # print(f"2) Light Intensity Buffer Status: {len(self.light_intensity_detection_buffer)}")
                    if len(self.light_intensity_detection_buffer) >= LOW_LIGHT_INTENSITY_DETECTION_BUFFER_SIZE:
                        darkness_count = Counter(self.darkness_buffer)
                        # print(f"3) Dark Frames Buffer Status: {darkness_count}")
                        if darkness_count[True] >= MAXIMUM_DARK_FRAMES:
                            self.too_dark = True
                            self.send_kafka_message(
                                message=f"ERROR {self.cam_name}: Inadequate lighting condition detected at {self.cam_name}. Halting recognition temporarily for {self.cam_name}."
                            )
                            self.adequate_lighting_message_sent = False
                            # print(f"4) Darkness Status: {self.too_dark}")
                            if not self.inadequate_lighting_message_logged:
                                multicam_server_logger.warn(f"Inadequate lighting condition detected at {self.cam_name}. Halting recognition temporarily for {self.cam_name}.")
                                # print(f"Inadequate lighting condition detected at {self.cam_name}. Halting recognition temporarily for {self.cam_name}.")
                                self.inadequate_lighting_message_logged = True

                            # time.sleep(IP_CAM_REINIT_WAIT_DURATION)

                        elif darkness_count[False] >= MAXIMUM_DARK_FRAMES and not self.adequate_lighting_message_sent:
                            multicam_server_logger.info(f"Lighting condition becomes adequate at {self.cam_name}. Recognition process resumed for {self.cam_name}.")
                            self.too_dark = False
                            self.send_kafka_message(
                                message=f"SUCCESS {self.cam_name}: Lighting condition becomes adequate at {self.cam_name}. Recognition process resumed for {self.cam_name}."
                            )
                            # print(f"Lighting condition becomes adequate at {self.cam_name}. Recognition process resumed for {self.cam_name}.")

                            # print("MESSAGE: Rise and Shine Buddy")
                            self.adequate_lighting_message_sent = True
                            self.inadequate_lighting_message_logged = False  # reset the flag
                            # print(f"5) Darkness Status: {self.too_dark}")

                        # Pop the first element from the buffers
                        self.light_intensity_detection_buffer.pop(0)
                        self.darkness_buffer.pop(0)
                        # print(f"6) Light Intensity Buffer Status: {len(self.light_intensity_detection_buffer)}")
                        # print(f"7) Dark Frames Buffer Status: {Counter(self.darkness_buffer)}")

                    if not self.too_dark:
                        self.shared_buffer.put((self.frame, self.cam_name, self.cam_ip))

                else:
                    self.shared_buffer.put((self.frame, self.cam_name, self.cam_ip))

                # frame_stats_manager.record_put(self.cam_name)

        else:
            self._read_and_discard_frame()
            # frame_stats_manager.record_discarded(self.cam_name)

        # toggle the flag to process alternate frames to improve the performance
        self.frame_counter += 1
        self.process_this_frame = (self.frame_counter % FRAME_RATE_FACTOR == 0)

    def send_kafka_message(self, message):
        """
        Sends a Kafka message when the camera is not accessible
        """
        # Produce the message
        self.producer.produce(topic=self.kafka_topic_name, partition=self.topic_partition, key=self.cam_name, value=message)

        # Flush the producer to ensure the message is sent
        self.producer.flush()


def create_camera(camera_name: str, camera_configuration: dict,  shared_buffer):
    """
    Creates a camera object and places the frames in the buffer

    Args:
        camera_name: Name of the camera to create
        camera_configuration (dict): Camera configuration
        shared_buffer: shared memory space to store the pre-processed frames

    Returns:
        None
    """
    global cameras

    cam = IPCamera(camera_name, camera_configuration, shared_buffer)
    cameras.append(cam)

    # Place the frames in the buffer until the end of the camera stream is reached
    while True:
        if cam.is_initialized:
            try:
                cam.place_frame_in_buffer()
            except Exception as error:
                # if an exception is raised, then release the camera stream and set the flag to False
                multicam_server_logger.error(
                    f'Exception raised while placing the frame in the buffer from {cam.cam_name} '
                    f'(url: {cam.cam_ip})) due to {error}. Releasing the stream...'
                )
                cam.release()
                cam.is_initialized = False
        else:
            # Message to be sent
            message = f"ERROR {cam.cam_name}: Camera stream from {cam.cam_name} is not accessible."
            # Send Kafka message
            cam.send_kafka_message(message=message)
            # print(message)

            # destroy the camera object since the camera stream was not initialized
            multicam_server_logger.error(f"Camera stream from {cam.cam_name} (url: {cam.cam_ip}) is not accessible. Destroying the camera object...")
            cameras.remove(cam)
            del cam
            # put the thread to sleep for 10 seconds
            multicam_server_logger.info(
                f"Putting the thread to sleep for {camera_name} (url: {camera_configuration['ip_address']}) for {IP_CAM_REINIT_WAIT_DURATION} seconds..."
            )
            time.sleep(IP_CAM_REINIT_WAIT_DURATION)
            # again try to recreate a new camera object
            multicam_server_logger.info(f"Creating a new camera object for {camera_name} (url: {camera_configuration['ip_address']})...")
            cam = IPCamera(camera_name, camera_configuration, shared_buffer)
            cameras.append(cam)

            if cam.is_initialized:
                # Message to be sent
                message = f"SUCCESS {cam.cam_name}: Camera {cam.cam_name} reconnection successful"
                cam.send_kafka_message(message=message)
                # print(message)


def producer_main(shared_buffer):
    with open(CAMERA_CONFIGURATION_FILE, "r") as camera_configuration_file:
        camera_configuration_data = json.load(camera_configuration_file)

    for location, points in camera_configuration_data.items():
        for point, cctv_cameras in points["cctv-cameras"].items():
            if not cctv_cameras:
                message = f"No CCTV Cameras installed for {point} point at {location}"
                # print(message)
                multicam_server_logger.info(message)
                continue

            for cctv_camera, cam_config in cctv_cameras.items():
                cam_name = f"{location}_{point}_{cctv_camera}"
                threading.Thread(target=create_camera, args=(cam_name, cam_config, shared_buffer)).start()

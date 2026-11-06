"""
This module is a server that performs face recognition (using the face_recognition library)
on multiple video streams

Reference for Multi-Processing Locking:
https://stackoverflow.com/questions/57095895/how-to-use-multiprocessing-queue-with-lock

Author: Anubhav Patrick and Hamza Aziz
Date: 2022-03-17
"""
import json
import os
import signal
import threading
import time
from collections import deque
import cv2

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
    DARKNESS_THRESHOLD, \
    LIGHTING_ALERT_SECONDS,     LOW_LIGHT_INTENSITY_DETECTION_BUFFER_SIZE, \
    MAXIMUM_DARK_FRAMES, \
    RESIZE_FRAME, \
    CAMERA_CONFIGURATION_FILE
from util.generic_utilities import map_camera_to_kafka_topic_and_partition, resize_roi_to_area, crop_and_mask_roi, \
    camera_stream_url
from util.video_source import open_stream

# A list of all the active cameras
cameras = []
# Progress slots (util/pipeline_health.Workers), set by src/main.py before this process forks; None in tests
workers = None
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
        self.roi = camera_config["masking-coordinates"]
        # Map camera to its corresponding kafka topic and partition
        self.kafka_topic_name, self.topic_partition = camera_to_topic_and_partition[self.cam_name]
        # Create Kafka Producer
        self.producer = create_kafka_producer()
        # initialize the video camera stream and read the first frame
        # The URL is shared with the ROI tool, so both open the camera the same way. VIDEO_DECODE picks the GPU or the
        # CPU decoder; a region of interest needs full frames, so the GPU does not scale those down
        self.stream = open_stream(camera_stream_url(camera_config), full_frame=CROP_ROI and self.roi is not None)
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
        self.reset_lighting()

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

    def reset_lighting(self):
        """Darkness state of a new stream: nothing judged yet."""
        self.darkness = deque(maxlen=LOW_LIGHT_INTENSITY_DETECTION_BUFFER_SIZE)
        self.too_dark = False
        self.last_lighting_alert = None
        self.last_region_alert = None

    @staticmethod
    def brightness(image, mask=None):
        """Mean grey level, 0 to 255; with a mask, over the mask's pixels only."""
        return cv2.mean(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), mask=mask)[0]

    def prepare(self, frame):
        """The frame recognition gets, and whether its picture is dark. With a region, only the region's own pixels are
        judged, at the camera's resolution: a bright lobby beside a dark door must not hide it, and resizing first would
        blend the black outside the region into its edge. Without one, a FRAME_WIDTH x FRAME_HEIGHT thumbnail is judged.
        Raises ValueError when the region does not fit the frame."""
        if CROP_ROI and self.roi is not None:
            roi, mask = crop_and_mask_roi(frame, self.roi, return_mask=True)
            dark = DARKNESS_DETECTION and self.brightness(roi, mask) < DARKNESS_THRESHOLD
            return resize_roi_to_area(roi), dark
        large = frame.shape[0] > FRAME_HEIGHT or frame.shape[1] > FRAME_WIDTH
        if RESIZE_FRAME and large:
            frame = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT), interpolation=cv2.INTER_AREA)
        elif DARKNESS_DETECTION and large:
            return frame, self.brightness(cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT), interpolation=cv2.INTER_AREA)) < DARKNESS_THRESHOLD
        return frame, DARKNESS_DETECTION and self.brightness(frame) < DARKNESS_THRESHOLD

    def lighting_allows(self, dark):
        """Records one frame's darkness and says whether the frame may go to recognition. The camera turns dark when
        MAXIMUM_DARK_FRAMES of the last LOW_LIGHT_INTENSITY_DETECTION_BUFFER_SIZE frames are dark, and light again when as
        many are light; in between it stays as it was. Until the window first fills, dark frames are held back and nothing
        is announced: streams often open on a few black frames."""
        if not DARKNESS_DETECTION:
            return True
        self.darkness.append(dark)
        if len(self.darkness) < self.darkness.maxlen:
            return not dark
        dark_frames = sum(self.darkness)
        if not self.too_dark and dark_frames >= MAXIMUM_DARK_FRAMES:
            self.too_dark = True
            multicam_server_logger.warning(f"Inadequate lighting condition detected at {self.cam_name}. Halting recognition temporarily for {self.cam_name}.")
        elif self.too_dark and len(self.darkness) - dark_frames >= MAXIMUM_DARK_FRAMES:
            self.too_dark = False
            self.last_lighting_alert = None
            multicam_server_logger.info(f"Lighting condition becomes adequate at {self.cam_name}. Recognition process resumed for {self.cam_name}.")
            self.send_kafka_message(
                message=f"SUCCESS {self.cam_name}: Lighting condition becomes adequate at {self.cam_name}. Recognition process resumed for {self.cam_name}."
            )
        # Once a frame was thousands of messages a minute. This pace keeps the alert on the display, which forgets a
        # camera's status whenever it reconnects to Kafka and relies on the re-send
        if self.too_dark and self.due(self.last_lighting_alert):
            self.last_lighting_alert = time.monotonic()
            self.send_kafka_message(
                message=f"ERROR {self.cam_name}: Inadequate lighting condition detected at {self.cam_name}. Halting recognition temporarily for {self.cam_name}."
            )
        return not self.too_dark

    @staticmethod
    def due(last_alert):
        return last_alert is None or time.monotonic() - last_alert >= LIGHTING_ALERT_SECONDS

    def alert_region(self, problem):
        """A region that does not fit the camera's picture: no recognition for that frame, an alert at the lighting pace."""
        if self.due(self.last_region_alert):
            self.last_region_alert = time.monotonic()
            multicam_server_logger.error(f"Region of interest of {self.cam_name} {problem}: frames skipped until it is redrawn")
            self.send_kafka_message(message=f"ERROR {self.cam_name}: Region of interest {problem}. Redraw it in the ROI page.")

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
                try:
                    self.frame, dark = self.prepare(self.frame)
                except ValueError as problem:  # the region does not fit this frame: say so and keep the stream open
                    self.alert_region(problem)
                else:
                    if self.lighting_allows(dark):
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

    if workers is not None:
        workers.beat("camera", camera_name)  # before the first open, which can take up to about 50 s
    cam = IPCamera(camera_name, camera_configuration, shared_buffer)
    cameras.append(cam)

    # Place the frames in the buffer until the end of the camera stream is reached
    while True:
        if workers is not None:
            workers.beat("camera", camera_name)  # every frame and every reconnect attempt: a hang stops it
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
            if workers is not None:
                workers.beat("camera", camera_name)
            # again try to recreate a new camera object
            multicam_server_logger.info(f"Creating a new camera object for {camera_name} (url: {camera_configuration['ip_address']})...")
            cam = IPCamera(camera_name, camera_configuration, shared_buffer)
            cameras.append(cam)

            if cam.is_initialized:
                # Message to be sent
                message = f"SUCCESS {cam.cam_name}: Camera {cam.cam_name} reconnection successful"
                cam.send_kafka_message(message=message)
                # print(message)


def configured_cameras(camera_configuration_data):
    """(camera name, its configuration) for every camera in the configuration, in a fixed order."""
    for location, points in camera_configuration_data.items():
        for point, cctv_cameras in points["cctv-cameras"].items():
            if not cctv_cameras:
                multicam_server_logger.info(f"No CCTV Cameras installed for {point} point at {location}")
                continue
            for cctv_camera, cam_config in cctv_cameras.items():
                yield f"{location}_{point}_{cctv_camera}", cam_config


def producer_main(shared_buffer):
    # Each camera has its own thread; OpenCV's own thread pool on top of them cost about 40% more CPU per frame, measured
    # on a 1080p stream. This process only runs the producer, so the consumer keeps its threads
    cv2.setNumThreads(1)
    # The parent's stop handler came across the fork, and failed here (it terminates a producer this process does not
    # own); the parent stops this process itself
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    with open(CAMERA_CONFIGURATION_FILE, "r") as camera_configuration_file:
        camera_configuration_data = json.load(camera_configuration_file)

    threads = []
    for cam_name, cam_config in configured_cameras(camera_configuration_data):
        threads.append(threading.Thread(target=create_camera, args=(cam_name, cam_config, shared_buffer), name=cam_name))
        threads[-1].start()

    # A camera thread only ends on an error its own loop does not catch; then this process exits, src/main.py sees it
    # and stops the container, and Docker starts it again
    while all(thread.is_alive() for thread in threads):
        time.sleep(5)
    multicam_server_logger.error(f"Camera thread(s) {[t.name for t in threads if not t.is_alive()]} died; stopping the producer")
    os._exit(1)

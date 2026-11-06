"""
This module is created to fetch frames from a shared buffer and collect them in batches for face recognition.

Original Author: Hamza Aziz
Modified by: Anubhav Patrick
"""

import multiprocessing
import threading
import time
from multiprocessing_shared_buffer import MULTIPROCESS_SHARED_BUFFER
from custom_logging import multicam_server_logger
from insightface_face_detection import IFRClient
from insightface_face_recognition import batched_frame_face_recognition

# Progress slots (util/pipeline_health.Workers), set by src/main.py before the threads start; None in tests
workers = None
from locks import lock
from multicam_stream_producer import cameras
from parameters import CAMERA_CONFIGURATION_FILE, \
    LIVE_STREAM_BUFFER_SIZE, \
    LIVE_STREAM_BUFFER_PURGE_SIZE, \
    BATCH_SIZE, \
    INSIGHTFACE_HOST, \
    INSIGHTFACE_PORT, \
    THREAD_FLAG, \
    MULTIPROCESSING_FLAG, \
    NUMBER_OF_THREADS, \
    NUMBER_OF_PROCESSES


def face_recognition(shared_buffer, thread_id: str, embeddings_collection, staging_collection):
    """
    This function gets frames from the shared buffer and collects them in batches for face recognition.

    Parameters:
        shared_buffer: A shared buffer that contains frames from all the cameras
        thread_id: The id of the thread that is calling this function
        embeddings_collection: A collection of embeddings of known faces
        staging_collection: A collection of embeddings of faces captured from CCTV footage
    """
    # One client per thread, kept for its lifetime: it replaces its own session after a connection error (IFRClient.extract)
    ifr_client = IFRClient(host=INSIGHTFACE_HOST, port=INSIGHTFACE_PORT)

    while True:
        if workers is not None:
            workers.beat("recognition", thread_id)  # waiting for frames is healthy, as long as this loop keeps turning
        # consumption_start_time = time.perf_counter()

        # Apply thread lock to the shared buffer
        with lock:
            # frame_accumulation_start_time = time.perf_counter()
            batch_ready = shared_buffer.qsize() >= BATCH_SIZE
            if batch_ready:
                batched_frame_buffer = []
                while len(batched_frame_buffer) != BATCH_SIZE:
                    camera_elements = shared_buffer.get()
                    # print(camera_elements)
                    batched_frame_buffer.append(camera_elements)
        if not batch_ready:
            # Waiting for a full batch used to spin a core, building a new client on every pass (about 93% CPU idle);
            # the lock is released while waiting
            time.sleep(0.01)
            continue
            # frame_accumulation_end_time = time.perf_counter()
            # frame_accumulation_total_time = frame_accumulation_end_time - frame_accumulation_start_time
            # print(
            #     f"Time taken to accumulate frames for batch of size {BATCH_SIZE} is "
            #     f"{frame_accumulation_total_time:>20.9f} seconds"
            # )
            # multicam_server_logger.debug(
            #     f"[CONSUMER] Time taken to accumulate frames for batch of size {BATCH_SIZE} is "
            #     f"{frame_accumulation_total_time:.6f} seconds"
            # )

        # extract batch of frames and camera names from the batched_frame_buffer
        # batch_extraction_start_time = time.perf_counter()
        batch_of_frames = [batch_elements[0] for batch_elements in batched_frame_buffer]
        batch_of_cam_names = [batch_elements[1] for batch_elements in batched_frame_buffer]
        batch_of_cam_ips = [batch_elements[2] for batch_elements in batched_frame_buffer]
        # batch_extraction_end_time = time.perf_counter()
        # batch_extraction_total_time = batch_extraction_end_time - batch_extraction_start_time
        # multicam_server_logger.debug(
        #     f"[CONSUMER] Time taken to extract batch of size {BATCH_SIZE} is {batch_extraction_total_time:.6f} seconds"
        # )

        # recognition_start_time = time.perf_counter()
        # Perform batched face recognition on the frames in the buffer
        ok = batched_frame_face_recognition(
            ifr_client=ifr_client,
            thread_name=thread_id,
            batch_of_frames=batch_of_frames,
            batch_of_cam_names=batch_of_cam_names,
            batch_of_cam_ips=batch_of_cam_ips,
            embeddings_collection=embeddings_collection,
            staging_collection=staging_collection
        )
        if workers is not None:
            workers.batch(thread_id, ok)
        # recognition_end_time = time.perf_counter()
        # recognition_total_time = recognition_end_time - recognition_start_time
        # multicam_server_logger.debug(
        #     f"[CONSUMER] Time taken to process batch of size {BATCH_SIZE} is {recognition_total_time:.6f} seconds"
        # )

        # Delete batch_of_frames
        del batch_of_frames

        frames_buffer_size = shared_buffer.qsize()
        # print(f"THREAD: {thread_id} CURRENT BUFFER SIZE: {frames_buffer_size}")
        if frames_buffer_size > LIVE_STREAM_BUFFER_SIZE:
            multicam_server_logger.warning(f"Frames buffer size {frames_buffer_size}. Purging frames_buffer...")
            for _ in range(LIVE_STREAM_BUFFER_PURGE_SIZE):
                shared_buffer.get()

        # consumption_end_time = time.perf_counter()
        # total_consumption_time = consumption_end_time - consumption_start_time
        # multicam_server_logger.debug(
        #     f"[CONSUMER] Total time taken by consumer to consume the whole batch is {total_consumption_time:.6f} seconds"
        # )


def threaded_gpu_face_recognition(shared_buffer, embeddings_collection, staging_collection):
    """
    This function creates threads for face recognition.

    Parameters:
        shared_buffer: A shared buffer that contains frames from all the cameras
        embeddings_collection: A collection of embeddings of known faces
        staging_collection: A collection of embeddings of faces captured from CCTV footage
    """
    num_of_threads = NUMBER_OF_THREADS
    threads = []
    for i in range(num_of_threads):
        threads.append(
            threading.Thread(
                target=face_recognition, args=(shared_buffer, f"thread_{i}", embeddings_collection, staging_collection), daemon=True
            )
        )

    for i in range(num_of_threads):
        if threads[i].is_alive() is False:
            # Start processes
            threads[i].start()

    # Handed back to src/main.py, which watches them and stops the container if one dies
    return threads


def multiprocess_gpu_face_recognition(shared_buffer, embeddings_collection, staging_collection):
    """
    This function creates processes for face recognition.

    Parameters:
        shared_buffer: A shared buffer that contains frames from all the cameras
        embeddings_collection: A collection of embeddings of known faces
        staging_collection: A collection of embeddings of faces captured from CCTV footage
    """
    num_of_processes = NUMBER_OF_PROCESSES
    processes = []
    for i in range(num_of_processes):
        processes.append(
            multiprocessing.Process(
                target=face_recognition, args=(shared_buffer, f"process_{i}", embeddings_collection, staging_collection), daemon=True
            )
        )

    for i in range(num_of_processes):
        if processes[i].is_alive() is False:
            # Start processes
            processes[i].start()

    # Keep the main thread running while camera threads process
    for i in range(num_of_processes):
        processes[i].join()


def consumer_main(shared_buffer, embeddings_collection, staging_collection):
    """
    This function starts the face recognition process.

    Parameters:
        shared_buffer: A shared buffer that contains frames from all the cameras
        embeddings_collection: A collection of embeddings of known faces
        staging_collection: A collection of embeddings of faces captured from CCTV footage
    """
    try:
        if THREAD_FLAG is True:
            # Start the face recognition thread
            return threaded_gpu_face_recognition(shared_buffer, embeddings_collection, staging_collection)
        elif MULTIPROCESSING_FLAG is True:
            # Start the face recognition thread
            multiprocess_gpu_face_recognition(shared_buffer, embeddings_collection, staging_collection)
        else:
            face_recognition(shared_buffer, 'no_thread', embeddings_collection, staging_collection)

    except KeyboardInterrupt:
        # Release the camera streams, store the dataframe in csv and exit the program
        for camera in cameras:
            camera.release()
            del camera
        multicam_server_logger.warning('Camera streams released')

        multicam_server_logger.warning("EXITING THE PROGRAM...")

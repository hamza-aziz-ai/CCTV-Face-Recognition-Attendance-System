#!/usr/bin/env python3
"""
dynamic_face_data_collector.py

Production-grade script for dynamic face data collection.

This module provides utilities to save face crops dynamically based on quality metrics
(pupil distance and matching score). It organizes saved faces into clusters per camera,
maintains metadata, and ensures only the best samples are stored.

Usage:
    from dynamic_face_data_collector import face_saver
    face_saver(cropped_faces_data)
"""
import os
import sys
import math
from datetime import datetime
from functools import reduce
from typing import Any, Dict, List, Tuple

import cv2

from postgresql_database_handler import insert_face_data, delete_face_data

# Add parent directory to the path to allow relative imports.
current = os.path.dirname(os.path.realpath(__file__))
parent = os.path.dirname(current)
sys.path.append(parent)

from parameters import (
    PUPIL_DISTANCE_THRESHOLD,
    DYNAMIC_DATASET_PATH,
    NUMBER_OF_PICTURES,
    METRIC_TYPE,
)
from util.generic_utilities import check_for_directory, load_metadata, save_metadata
from custom_logging import dynamic_face_data_collector_logger as logger

# Mapping of camera groups to cluster names
cluster_map: Dict[Tuple[str, str, str, str, str], str] = {
    (
        "maingate_entry_cctv-camera-1",
        "maingate_entry_cctv-camera-2",
        "maingate_entry_cctv-camera-3",
        "maingate_entry_cctv-camera-4",
        "maingate_entry_cctv-camera-5",
    ): "cluster-1",
    (
        "maingate_entry_cctv-camera-6",
        "maingate_entry_cctv-camera-7",
        "maingate_entry_cctv-camera-8",
        "maingate_entry_cctv-camera-9",
        "maingate_entry_cctv-camera-10",
    ): "cluster-2",
    (
        "maingate_exit_cctv-camera-1",
        "maingate_exit_cctv-camera-2",
        "maingate_exit_cctv-camera-3",
        "maingate_exit_cctv-camera-4",
        "maingate_exit_cctv-camera-5",
    ): "cluster-3",
    (
        "maingate_exit_cctv-camera-6",
        "maingate_exit_cctv-camera-7",
        "maingate_exit_cctv-camera-8",
        "maingate_exit_cctv-camera-9",
        "maingate_exit_cctv-camera-10",
    ): "cluster-4",
}

# Flattened map for quick lookup
flat_map: Dict[str, str] = {
    camera: cluster for cameras, cluster in cluster_map.items() for camera in cameras
}


def get_cluster(camera_name: str) -> str:
    """
    Retrieve the cluster name for a given camera.

    Args:
        camera_name: Identifier of the camera.

    Returns:
        Name of the cluster to which the camera belongs.

    Raises:
        KeyError: If the camera_name is not recognized.
    """
    try:
        cluster = flat_map[camera_name]
        logger.debug(f"Camera '{camera_name}' mapped to cluster '{cluster}'")
        return cluster
    except KeyError as err:
        logger.error(f"Unknown camera: {camera_name}")
        raise KeyError(f"Unknown camera: {camera_name}") from err


def is_worse(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    """
    Determine if entry `a` is strictly worse than entry `b`.

    Comparison is based on pupil distance and match score, according to the configured METRIC_TYPE.

    Args:
        a: Metadata entry with keys 'pupil_distance' and 'match_score'.
        b: Metadata entry to compare against.

    Returns:
        True if `a` is worse than `b`.
    """
    # Compare pupil distances (larger is better)
    if a["pupil_distance"] != b["pupil_distance"]:
        return a["pupil_distance"] < b["pupil_distance"]

    # If pupil distances are equal, compare match scores based on metric type
    if METRIC_TYPE == "L2":
        # Lower L2 distance is better
        return a["match_score"] > b["match_score"]
    elif METRIC_TYPE == "COSINE":
        # Higher cosine similarity is better
        return a["match_score"] < b["match_score"]
    else:
        logger.warning(f"Unsupported METRIC_TYPE '{METRIC_TYPE}', defaulting to COSINE behavior.")
        return a["match_score"] < b["match_score"]


def save_face_if_better(
        person_id: str,
        camera_name: str,
        face_crop: Any,
        pupil_distance: float,
        face_matching_score: float,
):
    """
    Save the face crop for a given person if it is among the best according to quality metrics.

    This function maintains a fixed-size dataset per person and cluster. If the dataset
    is not full, it simply adds the new crop. Once full, it replaces the worst sample
    if the new one is better.

    Args:
        person_id: Unique identifier for the person.
        camera_name: Name of the camera capturing the face.
        face_crop: Image array of the cropped face.
        pupil_distance: Distance between pupils (indicates face size/quality).
        face_matching_score: Score from face matcher (lower/higher is better based on METRIC_TYPE).
    """
    # Determine storage directory based on person and camera cluster
    cluster_name = get_cluster(camera_name)
    save_dir = os.path.join(DYNAMIC_DATASET_PATH, person_id, cluster_name)
    check_for_directory(save_dir)
    metadata_path = os.path.join(save_dir, "meta.json")
    metadata = load_metadata(metadata_path)

    # Prepare new entry template
    new_entry: Dict[str, Any] = {
        "filename": None,
        "pupil_distance": pupil_distance,
        "match_score": face_matching_score,
    }

    if pupil_distance < PUPIL_DISTANCE_THRESHOLD:
        logger.debug(
            f"Skipping record for {person_id}: pupil distance {pupil_distance:.2f} "
            f"is below threshold {PUPIL_DISTANCE_THRESHOLD}"
        )
    else:
        try:
            while len(metadata) >= NUMBER_OF_PICTURES:
                # Find the worst sample in current metadata
                worst_entry = reduce(lambda w, e: e if is_worse(e, w) else w, metadata)
                # Determine if new entry is better than the worst
                better = (
                        pupil_distance > worst_entry["pupil_distance"]
                        or (
                                pupil_distance == worst_entry["pupil_distance"]
                                and not is_worse({"pupil_distance": pupil_distance, "match_score": face_matching_score}, worst_entry)
                        )
                )

                if better:
                    worst_path = os.path.join(save_dir, worst_entry["filename"])
                    if os.path.exists(worst_path):
                        os.remove(worst_path)
                        logger.info(f"Removed worst face image: {worst_path}")
                    metadata.remove(worst_entry)
                    delete_face_data(person_id, worst_path, cluster_name)

            filename = datetime.now().strftime("%Y%m%d_%H%M%S_%f.jpg")
            new_entry["filename"] = filename
            file_path = os.path.join(save_dir, filename)
            try:
                cv2.imwrite(file_path, face_crop)
                metadata.append(new_entry)
                insert_face_data(person_id, file_path, camera_name, cluster_name, pupil_distance, face_matching_score)
                save_metadata(metadata_path, metadata)
                logger.info(f"Updated facial dataset for {person_id}. Image saved at {file_path}, metadata updated at {metadata_path}")
            except Exception as error:
                logger.error(f"Unable to update face data for {person_id} at {file_path} due to error: {error}")

        except Exception as exc:
            logger.error(
                f"Failed to save face for {person_id} from {camera_name}: {exc}"
            )

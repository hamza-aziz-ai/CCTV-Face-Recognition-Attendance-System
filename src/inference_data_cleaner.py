"""
This module is created to clean and format the inference data of insightface_face_recognition
"""
import cv2
import base64
from parameters import FACE_MATCHING_TOLERANCE, METRIC_TYPE, STAGING


def calculate_euclidean_percentage_similarity(euclidean_distance):
    if euclidean_distance <= FACE_MATCHING_TOLERANCE:
        # For distances between 0 and 0.9, similarity is 100%
        return 100
    else:
        # For distances > 0.9, calculate decreasing similarity
        # Adjusting the range to start decreasing from 0.9 up to 2
        max_distance = 2
        # Scaling the distance beyond 0.9 to fit within the (0 to 1) range
        adjusted_distance = (euclidean_distance - FACE_MATCHING_TOLERANCE) / (max_distance - FACE_MATCHING_TOLERANCE)
        percentage_similarity = (1 - adjusted_distance) * 100
        return max(0, percentage_similarity)  # Ensuring it doesn't go negative


def calculate_cosine_percentage_similarity(cosine_distance):
    if cosine_distance >= FACE_MATCHING_TOLERANCE:
        # For distances >= 0.48, similarity is 100%
        return 100
    else:
        # For distances < 0.48, similarity decreases as distance decreases
        # Scaling the distance from 0 to 0.48 for linear decrease
        adjusted_similarity = (cosine_distance / FACE_MATCHING_TOLERANCE) * 100
        return max(0, adjusted_similarity)  # Ensuring non-negative similarity


def collect_cropped_face_data(inference_result, camera_list: list, face_array_list: list, landmarks_list: list) -> dict:
    """
    This function formats the raw inference data of a single batch and cleans it for further use.

    Arguments:
        face_array_list: A List of cropped faces who were detected in a single batch
        inference_result: Raw inference result of single batch
        camera_list
        landmarks_list

    Returns:
        single_batch_result: A list of cropped faces corresponding to the person recognized in a single batch in dictionary format
    """

    single_batch_result = dict()

    for i, hit in enumerate(inference_result):
        name_of_person = hit[0].id
        cropped_face = face_array_list[i]
        camera_name = camera_list[i]
        landmarks = landmarks_list[i]

        # If using L2 (Euclidean Distance) for face recognition
        if METRIC_TYPE == "L2":
            euclidean_distance = hit[0].distance
            if euclidean_distance <= FACE_MATCHING_TOLERANCE:
                if name_of_person not in single_batch_result:
                    single_batch_result[name_of_person] = [(cropped_face, euclidean_distance, camera_name, landmarks)]
                else:
                    single_batch_result[name_of_person].append((cropped_face, euclidean_distance, camera_name, landmarks))

        # If using COSINE metric type for face recognition
        elif METRIC_TYPE == "COSINE":
            cosine_similarity = hit[0].distance
            if cosine_similarity >= FACE_MATCHING_TOLERANCE:
                if name_of_person not in single_batch_result:
                    single_batch_result[name_of_person] = [(cropped_face, cosine_similarity, camera_name, landmarks)]
                else:
                    single_batch_result[name_of_person].append((cropped_face, cosine_similarity, camera_name, landmarks))

    # print(single_batch_result)
    return single_batch_result


def data_formatter(inference_result, staging_result,
                   camera_list: list, ip_list: list,
                   frame_list: list, bbox_list: list) -> dict:
    """
    Formats a batch of embeddings searches against two collections:
      - inference_result: top-5 hits from the main (original) collection
      - staging_result: top-5 hits from the staging collection

    For each detected face:
      1. If original_hits[0] passes the threshold, use that.
      2. Else if STAGING=True, intersect the two hit‐lists by id,
         and pick the “best” among that intersection from original_hits.
    """
    single_batch_result = {}

    for i, (orig_hits, stag_hits) in enumerate(zip(inference_result, staging_result)):
        cam_name = camera_list[i]
        cam_ip   = ip_list[i]
        _, buffer = cv2.imencode(".jpg", frame_list[i])
        frame_base64 = base64.b64encode(buffer.tobytes()).decode("ascii")
        bbox = bbox_list[i]

        # 1) Try the best original hit
        if orig_hits:
            top = orig_hits[0]
            dist = top.distance
            pid  = top.id

            good_orig = (
                (METRIC_TYPE=="L2"    and dist <= FACE_MATCHING_TOLERANCE) or
                (METRIC_TYPE=="COSINE" and dist >= FACE_MATCHING_TOLERANCE)
            )
            if good_orig:
                single_batch_result.setdefault(pid, []).append(
                    (cam_name, cam_ip, dist, frame_base64, bbox)
                )
                continue

        # 2) Fallback: find intersection if staging is enabled
        if STAGING and orig_hits and stag_hits:
            # multicam_server_logger.debug(f"Matching from original dataset failed. Falling back to staging logic")
            # map id→distance from original
            orig_map = { h.id: h.distance for h in orig_hits }
            # set of ids from staging
            stag_ids = { h.id for h in stag_hits }
            common  = set(orig_map) & stag_ids

            if common:
                # choose best in common by the same metric
                if METRIC_TYPE == "L2":
                    best_id = min(common, key=lambda x: orig_map[x])
                else:  # COSINE
                    best_id = max(common, key=lambda x: orig_map[x])

                best_dist = orig_map[best_id]
                # ** threshold check here **
                good_staging = (
                        (METRIC_TYPE == "L2" and best_dist <= FACE_MATCHING_TOLERANCE + 0.05) or
                        (METRIC_TYPE == "COSINE" and best_dist >= FACE_MATCHING_TOLERANCE - 0.05)
                )
                if good_staging:
                    single_batch_result.setdefault(best_id, []).append(
                        (cam_name, cam_ip, best_dist, frame_base64, bbox)
                    )

        # else: no match added for this face

    return single_batch_result



def feedback_data_formatter(inference_result, camera_list: list, ip_list: list) -> dict:
    """
    This function formats the raw inference data of a single batch and cleans it for further use.

    Arguments:
        inference_result: Raw inference result of single batch
        camera_list: List of cameras corresponding to the inference results
        ip_list: List of ip addresses corresponding to the inference results

    Returns:
        single_batch_result: Processed inference result of single batch in a dictionary format
    """

    single_batch_result = {}

    for i, hit in enumerate(inference_result):
        name_of_person = hit[0].id
        cam_name = camera_list[i]
        cam_ip = ip_list[i]

        # If using L2 (Euclidean Distance) for face recognition
        if METRIC_TYPE == "L2":
            euclidean_distance = hit[0].distance
            percentage_similarity = calculate_euclidean_percentage_similarity(euclidean_distance)
            if euclidean_distance <= FACE_MATCHING_TOLERANCE:
                is_recognized = True
                if name_of_person not in single_batch_result:
                    single_batch_result[name_of_person] = [(cam_name, cam_ip, euclidean_distance, is_recognized)]
                else:
                    single_batch_result[name_of_person].append((cam_name, cam_ip, euclidean_distance, is_recognized))
        # If using COSINE metric type for face recognition
        elif METRIC_TYPE == "COSINE":
            cosine_similarity = hit[0].distance
            percentage_similarity = calculate_cosine_percentage_similarity(cosine_similarity)
            if cosine_similarity >= FACE_MATCHING_TOLERANCE:
                is_recognized = True
                if name_of_person not in single_batch_result:
                    single_batch_result[name_of_person] = [(cam_name, cam_ip, cosine_similarity, is_recognized)]
                else:
                    single_batch_result[name_of_person].append((cam_name, cam_ip, cosine_similarity, is_recognized))

    return single_batch_result

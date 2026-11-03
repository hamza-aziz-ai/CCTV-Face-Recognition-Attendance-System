"""Checks a person's enrolment photos before anything reaches Milvus (D-026).

Each function returns a list of problems; an empty list means the check passed. Plain logic with no project imports,
so CI can run the self-check at the bottom: python -I src/util/enrolment_checks.py
"""
import math

POSES = ("front", "chin_up", "chin_down", "left_30", "right_30")
GLASSES = tuple(f"{pose}_glasses" for pose in POSES)


def check_files(stems):
    """All 5 poses are required; the 5 spectacles poses are all-or-nothing."""
    names = set(stems)
    problems = [f"missing photo: {pose}" for pose in POSES if pose not in names]
    if names & set(GLASSES):
        problems += [f"missing photo: {pose}" for pose in GLASSES if pose not in names]
    problems += [f"unexpected photo: {name}" for name in sorted(names - set(POSES) - set(GLASSES))]
    return problems


def check_face(stem, faces, min_confidence, min_pupil_px):
    """Exactly one face, because every detected face would be enrolled under this person's name."""
    if len(faces) != 1:
        return [f"{stem}: expected 1 face, found {len(faces)}"]
    face = faces[0]
    problems = []
    if face["prob"] < min_confidence:
        problems.append(f"{stem}: face confidence {face['prob']:.2f} is below {min_confidence}")
    left_eye, right_eye = face["landmarks"][:2]
    pupils = math.dist(left_eye, right_eye)
    if pupils < min_pupil_px:
        problems.append(f"{stem}: pupils are {pupils:.0f} px apart, below {min_pupil_px}")
    return problems


def check_photo_file(stem, data, max_bytes, short_side, min_short_side):
    """An uploaded photo: a JPEG within the size limit, large enough for a usable face."""
    problems = []
    if len(data) > max_bytes:
        problems.append(f"{stem}: {len(data) // 1024} KB is over the {max_bytes // 1024} KB limit")
    if not data.startswith(b"\xff\xd8\xff"):
        problems.append(f"{stem}: not a JPEG")
    elif short_side < min_short_side:
        problems.append(f"{stem}: the short side is {short_side} px, below {min_short_side}")
    return problems


def head_pose(landmarks):
    """(turn, tilt) from InsightFace's 5 landmarks (eyes, nose, mouth corners), both scale-free.
    turn: the nose's sideways offset from between the eyes, over the eye distance; positive is the person's left.
    tilt: the nose's height between the eye line (0) and the mouth line (1); lower is chin up."""
    (lx, ly), (rx, ry), (nx, ny), (mlx, mly), (mrx, mry) = landmarks[:5]
    eye_x, eye_y = (lx + rx) / 2, (ly + ry) / 2
    mouth_y = (mly + mry) / 2
    return (nx - eye_x) / math.dist((lx, ly), (rx, ry)), (ny - eye_y) / (mouth_y - eye_y)


def check_poses(landmarks, min_turn, min_tilt, max_front_turn):
    """Each pose against the same set's front photo, as faces differ: left and right must turn at least min_turn the
    right way, chin up and down tilt at least min_tilt, and the front photo must face the camera. landmarks: {stem: 5
    points}. Thresholds were calibrated on one person's real photos (2026-11-03), so they are provisional."""
    problems = []
    for suffix in ("", "_glasses"):
        if f"front{suffix}" not in landmarks:
            continue
        front_turn, front_tilt = head_pose(landmarks[f"front{suffix}"])
        if abs(front_turn) > max_front_turn:
            problems.append(f"front{suffix}: the head is turned ({front_turn:+.2f}), face the camera")
        wanted = {"left_30": (0, 1, "turned to the left"), "right_30": (0, -1, "turned to the right"),
                  "chin_down": (1, 1, "tilted down"), "chin_up": (1, -1, "tilted up")}
        for pose, (axis, sign, words) in wanted.items():
            stem = f"{pose}{suffix}"
            if stem not in landmarks:
                continue
            change = (head_pose(landmarks[stem])[axis] - (front_tilt if axis else front_turn)) * sign
            if change < (min_tilt if axis else min_turn):
                problems.append(f"{stem}: not {words} enough compared with the front photo ({change:+.2f})")
    return problems


def check_sharpness(stem, sharpness, minimum):
    """sharpness: variance of the Laplacian of the face, scaled to 112 x 112, so it does not depend on photo size."""
    return [f"{stem}: the face is blurred (sharpness {sharpness:.0f}, below {minimum})"] if sharpness < minimum else []


def cosine(a, b):
    return sum(x * y for x, y in zip(a, b)) / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


def check_same_person(vectors, tolerance):
    """Each photo must match the person's other photos, which catches someone else's photo in the folder."""
    problems = []
    for stem, vector in vectors.items():
        scores = sorted(cosine(vector, other) for name, other in vectors.items() if name != stem)
        median = scores[len(scores) // 2]
        if median < tolerance:
            problems.append(f"{stem}: does not match this person's other photos ({median:.2f} is below {tolerance})")
    return problems


def check_not_enrolled(matches, person_id, tolerance):
    """matches: {stem: (enrolled id, similarity)}. A match to someone else means a duplicate or a mixed-up ID."""
    return [f"{stem}: matches already enrolled {name} ({score:.2f})"
            for stem, (name, score) in matches.items() if name != person_id and score >= tolerance]


def demo():
    assert check_files(POSES) == []
    assert check_files(POSES + GLASSES) == []
    assert check_files(POSES[:4]) == ["missing photo: right_30"]
    assert check_files(POSES + ("front_glasses",))[0] == "missing photo: chin_up_glasses"
    assert check_files(POSES + ("selfie",)) == ["unexpected photo: selfie"]

    face = {"prob": 0.9, "landmarks": [[0, 0], [40, 0]]}
    assert check_face("front", [face], 0.7, 28) == []
    assert "found 2" in check_face("front", [face, face], 0.7, 28)[0]
    assert "found 0" in check_face("front", [], 0.7, 28)[0]
    assert "confidence" in check_face("front", [{**face, "prob": 0.5}], 0.7, 28)[0]
    assert "pupils" in check_face("front", [{**face, "landmarks": [[0, 0], [20, 0]]}], 0.7, 28)[0]

    assert check_photo_file("front", b"\xff\xd8\xff" + b"x" * 10, 2048, 600, 480) == []
    assert "over the" in check_photo_file("front", b"\xff\xd8\xff" + b"x" * 3000, 2048, 600, 480)[0]
    assert check_photo_file("front", b"\x89PNG", 2048, 600, 480) == ["front: not a JPEG"]
    assert "short side" in check_photo_file("front", b"\xff\xd8\xff", 2048, 400, 480)[0]

    # Landmarks shaped like the owner's real photos: eyes 100 px apart, mouth 100 px below them
    def face(nose_x, nose_y):
        return [[0, 0], [100, 0], [nose_x, nose_y], [10, 100], [90, 100]]
    real = {"front": face(47, 42), "left_30": face(61, 43), "right_30": face(34, 43), "chin_up": face(48, 36),
            "chin_down": face(49, 59)}
    assert head_pose(real["front"]) == (-0.03, 0.42)
    assert check_poses(real, 0.08, 0.04, 0.10) == []
    swapped = {**real, "left_30": real["right_30"], "right_30": real["left_30"]}
    assert [p.split(":")[0] for p in check_poses(swapped, 0.08, 0.04, 0.10)] == ["left_30", "right_30"]
    assert "chin_up" in check_poses({**real, "chin_up": real["front"]}, 0.08, 0.04, 0.10)[0]
    assert "face the camera" in check_poses({**real, "front": face(70, 42)}, 0.08, 0.04, 0.10)[0]
    assert check_poses({**real, **{f"{k}_glasses": v for k, v in real.items()}}, 0.08, 0.04, 0.10) == []
    assert check_sharpness("front", 407, 40) == [] and "blurred" in check_sharpness("front", 20, 40)[0]

    me = {"front": [1.0, 0.1], "chin_up": [0.9, 0.2], "chin_down": [0.95, 0.15]}
    assert check_same_person(me, 0.5) == []
    assert "stranger" in check_same_person({**me, "stranger": [-1.0, 0.1]}, 0.5)[0]

    assert check_not_enrolled({"front": ("hamza_aziz", 0.9)}, "hamza_aziz", 0.5) == []
    assert check_not_enrolled({"front": ("someone", 0.3)}, "hamza_aziz", 0.5) == []
    assert "someone" in check_not_enrolled({"front": ("someone", 0.8)}, "hamza_aziz", 0.5)[0]
    print("enrolment checks ok")


if __name__ == "__main__":
    demo()

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

    me = {"front": [1.0, 0.1], "chin_up": [0.9, 0.2], "chin_down": [0.95, 0.15]}
    assert check_same_person(me, 0.5) == []
    assert "stranger" in check_same_person({**me, "stranger": [-1.0, 0.1]}, 0.5)[0]

    assert check_not_enrolled({"front": ("hamza_aziz", 0.9)}, "hamza_aziz", 0.5) == []
    assert check_not_enrolled({"front": ("someone", 0.3)}, "hamza_aziz", 0.5) == []
    assert "someone" in check_not_enrolled({"front": ("someone", 0.8)}, "hamza_aziz", 0.5)[0]
    print("enrolment checks ok")


if __name__ == "__main__":
    demo()

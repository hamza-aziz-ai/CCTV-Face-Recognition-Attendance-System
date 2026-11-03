# Department matching and the metric toggle

Roadmap 8f, D-049. In an organisation whose departments are physically separate, a department's cameras recognise only that department's people.

## Setting it up

1. Give cameras a department in `camera_configuration.json`: either `"department": "Stores"` on a location, which covers all its cameras, or on a single camera, which overrides its location's. A camera without one, such as the main gate, searches everyone. Restart `producer-consumer` to apply.
2. People take the department they were registered with in the enrolment app. To add others, or to make someone recognisable everywhere, run this in the API container:
   ```bash
   python3 src/api/enrolment.py departments EMP-1042 Dispatch Stores   # other departments; "all" for every camera; none to clear
   ```
3. Publish so cameras follow (the enrolment worker also does this at every accepted enrolment):
   ```bash
   python3 src/util/face_vectors.py publish
   ```

Department names are compared trimmed and in lowercase.

## Rules (owner, 2026-11-03)

- A department camera finds only people in its department, or in "all". When none of them matches, the face stays unrecognised: there is no fallback to the whole organisation.
- A person may be in several departments.
- A person with no department is found only by cameras without one.

## The metric toggle

Set in master.env, then restart `producer-consumer`:

| `MATCH_METRIC` | Threshold | Default | Behaviour seen by the owner |
|---|---|---|---|
| `COSINE` | `COSINE_THRESHOLD`: a match needs at least this | 0.5 | Rarely misses; at 0.45, a rare wrong match |
| `L2` | `L2_THRESHOLD`: a match needs at most this squared distance | 0.95 | Misses more; no wrong match seen |

Both use the same vectors and the same collection. The vectors are unit length, so squared L2 = 2 - 2 x cosine, and an L2 threshold t is the cosine threshold 1 - t/2: 0.95 is 0.525. Scores are recorded as cosine in both modes.

## Checks

`python3 src/util/face_vectors.py demo` checks department lists and the search grouping. On 2026-11-03 against the laptop's Milvus (GPU_IVF_FLAT), with a temporary collection: each face matched only within its camera's department, a person in "all" was found by a department camera, a camera without a department found the person with none, a dispatch-only person's face at a stores camera came back only as stores people (best 0.107), and squared L2 equalled 2 - 2 x cosine.

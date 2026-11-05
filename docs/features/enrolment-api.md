# Enrolment API

The server side of the enrolment app's contract (roadmap 8c, D-048; the app is Face-Dataset-Collector, FEATURE-001). Staff sign in on the app, pick a person from the client's roster, record consent, and upload 5 pose photos, or 10 with glasses. The server checks them, keeps them in the client's own bucket, and publishes the person's vectors to Milvus.

## Routes

Through the proxy as `https://<site host>/api/...`; the proxy strips `/api`.

| Route | Who | What |
|---|---|---|
| `POST /api/auth/token` | anyone with an account | `{username, password}` to `{token, role, expires_at}`, for an `Authorization: Bearer` header. Browsers keep the cookie login at `/api/auth/login`. |
| `GET /api/v1/server-info` | no login | `{client_id, client_name, notice_version, notice_url, deletion_days}`; `deletion_days` is 90, the notice's promise |
| `GET /api/v1/notice` | no login | The client's notice from the site's `enrolment/notice.json`, or 503 `no_notice` until it exists |
| `GET /api/v1/persons?query=&limit=50&cursor=` | `client_admin`, `enrolment_operator` | The roster, paged by `person_id`, with `enrolment_status` `none`, `pending` or `enrolled` |
| `POST /api/v1/persons` | `client_admin`, `enrolment_operator` | Registers a person: `{person_id, name, department?}` to 201 `{person_id}`. `person_id` is the organisational or institutional ID: a letter or digit first, then up to 63 of `A-Z a-z 0-9 . _ -`, no Windows device names (`CON`, `NUL`, `COM1`...), unique in any letter case (409 `person_exists`). `name` is 1 to 120 characters. |
| `POST /api/v1/consents` | same | `{person_id, notice_version, captured_at, method: "staff_attested_in_app"}` to 201 `{consent_id}` |
| `DELETE /api/v1/consents/{id}` | same | Withdraws the consent and cancels its open job, deleting its photos; 202 `{deletion_id}`. If it is the consent the accepted enrolment rests on, the person's face data is deleted too, as below, and `deletion_id` names that deletion. During a re-enrolment, withdrawing the new attempt's consent ends only that attempt. |
| `DELETE /api/v1/persons/{id}/enrolment?reason=withdrawn\|left` | same | The person withdraws or leaves: every consent ends, an open job is cancelled, `enrolment_status` goes back to `none`, and their face data is deleted (below). 202 `{deletion_id}`; asking again while it runs returns the same ID. 404 `person_not_found`, 422 `invalid_reason`. Consent for them is refused with 409 `deletion_pending` until it is done; then the ID can be registered again. |
| `POST /api/v1/enrolments` | same | Multipart: `person_id`, `consent_id`, optional `reason`, one part per pose named by the pose. Needs `Idempotency-Key`. 202 `{job_id}` once every photo is in the bucket and the job is committed. |
| `GET /api/v1/enrolments/{job_id}` | same | `{status: pending\|accepted\|rejected, problems: [{pose, problem, code}]}`; `pose` is null for a set-level problem. `problem` is text for display; `code` is stable for the app to act on: `already_enrolled` (a retake can't fix it; check the roster), `photo_set`, `file`, `too_small`, `face_count`, `low_confidence`, `blurred`, `mismatch`, `pose`, `expired`, `withdrawn`, or `other`. Jobs from before 2026-11-04 have no `code`. |

Errors are `{"error": code}`, the codes the app maps: `signed_out` (401), `role_cannot_enrol` (403), `no_notice` (503), `notice_version_superseded`, `no_active_consent`, `invalid_pose_set`, `not_jpeg`, `reason_required`, `invalid_reason` (422), `photo_too_large`, `body_too_large` (413), `idempotency_key_required` (400), `idempotency_key_reused` (409), `enrolment_open` (409, with the open `job_id`), `person_not_found` (404) and `deletion_pending` (409). The same key with the same body returns the same job.

## The notice: who is responsible, per deployment

Who is responsible for the data (`controller`, with an optional `processor`) and whom to contact (`contact`: `name`, `email`, optional `phone`) come only from the site's `enrolment/notice.json`. The code names nobody, and the app shows whatever the file says (owner, 2026-11-03).

- Dedicated deployment: copy `enrolment/notice.dedicated.example.json`. The client organisation is responsible and is the contact; the operator does not appear.
- Central deployment: copy `enrolment/notice.central.example.json`. The operator (the owner, or their company once it exists) is responsible and is the contact.
- The owner's own site names the owner.

The API refuses to serve a notice with no version, controller, contact name or contact email, or with a template `<placeholder>` left in, and answers `no_notice`, so nobody consents to an unfilled notice. Each consent stores the notice as it was shown, so the record keeps who was responsible at the time. Whether the operator in a central deployment is the controller or a processor under India's DPDP Act is part of the legal advice still needed (Face-Dataset-Collector D-005).

## On the display

The display shows the person's ID large and the registered name beneath it (owner, 2026-11-03). The portrait server answers `POST /post_names` with `{"messages": [ids]}` beside `/post_images`: a JSON object with every requested ID and its name as a plain string, or null when unknown or when the database cannot be reached. Names are never logged; a failed lookup logs only the error type. A display that gets no name shows the ID alone.

Besides registration in the app, the roster can be filled in the API container:

```bash
python3 src/api/enrolment.py add-person PERSON_ID "NAME" [EMPLOYEE_CODE] [DEPARTMENT]
python3 src/api/enrolment.py import-persons persons.csv    # person_id,name,employee_code,department
python3 src/api/enrolment.py departments PERSON_ID [DEPARTMENT ...]    # departments besides the registered one, or "all" (docs/features/department-matching.md)
```

## Checks

The API refuses a wrong pose set, a non-JPEG and an oversized photo at once. The enrolment worker then checks every photo (`src/util/enrol_person.py` `check_photos`, the same code the command-line enrolment uses):

- JPEG, at most 2,000,000 bytes, short side at least 480 px.
- Exactly 1 face, detection confidence at least 0.7, pupils at least 28 px apart.
- Face sharpness at least 40: the Laplacian variance of the face scaled to 112 x 112.
- Head pose against the same set's front photo, from InsightFace's 5 landmarks: `left_30` and `right_30` turn at least 0.08 of the eye distance the right way, `chin_up` and `chin_down` tilt at least 0.04, and `front` faces the camera within 0.10. Swapped left and right are caught.
- Every photo matches the person's other photos, and none matches someone else already enrolled. The reply says only "matches someone already enrolled"; the server log names who, for the admin (data minimisation).

The pose and blur limits were calibrated on one person's 10 real photos on 2026-11-03, so they are provisional: those photos turned 0.12 to 0.17 sideways, tilted 0.06 to 0.19, and scored 330 to 595 sharp, while 3 px of added blur scored 54 and 5 px scored 20.

## Storage and publishing

- Uploads go to the client's own bucket, `<client>-enrolment`, under `jobs/<job_id>/<pose>.jpg`, with the client's own key (D-037).
- `enrolment-worker` (the producer-consumer image) takes the oldest pending job, locked so a second worker skips it.
- Rejected: the photos are deleted at once and only the reasons stay. A job still pending after 24 hours expires the same way.
- Accepted: the photos move to `persons/<person_id>/`, the vectors are saved to the site's `FACIAL-RECOGNITION-DATASET/<person_id>/vectors.parquet`, and `face_vectors.publish` rebuilds Milvus (D-030) under a PostgreSQL advisory lock, so two publishes never race. A re-enrolment replaces the person's vectors and photos.

## Deletion (8e)

Notice 1.2 promises that a person's face data goes within 90 days of withdrawing or leaving, that attendance records stay, and that the camera pictures on them are deleted 3 years after that (owner, 2026-11-03). The API records each request in `deletions`; `enrolment-worker` carries it out as soon as it sees it (`src/util/enrolment_deletion.py`):

- The bucket: `persons/<person_id>/` and every job's photos.
- The site's folders: `FACIAL-RECOGNITION-DATASET/<person_id>/` (vectors), `DYNAMIC-FACIAL-RECOGNITION-DATASET/<person_id>/` (nightly crops) and `DISPLAY-FACE-DATASET/<person_id>/` (portrait), and their vectors in the nightly `dynamic-dataset.pkl`.
- The nightly collector's rows in its own database: `face_images` and `person_summary`.
- Milvus (`face_vectors.forget`): a new version without them, empty if they were the last, then every other version is dropped, since any older one may hold them; a rollback after a deletion is rebuilt from the dataset. Their rows in the staging collection go too.
- Last, their roster row, consents and jobs. Every step can run again, so a deletion that fails part-way stays open and is retried whole.

The request row stays, with the person's ID only. Each hour the worker clears `recognition_frame` on the person's `recognition_results` rows dated up to the request, once it is 3 years old; the records themselves stay, and records made after the ID was registered again keep their pictures. `deploy/recovery.py restore` reads the live database's deletions before it drops it and re-runs them on the restored data, so a snapshot taken before a deletion cannot bring anyone back.

## Proven on the laptop (2026-11-03)

Through the HTTPS proxy with a temporary operator account: `/auth/token`, consent, and an upload of the owner's 10 photos under a new person ID was rejected in 4 s as matching someone already enrolled. The same photos for `hamza_aziz` were accepted in 14 s: Milvus moved to a new version with 10 rows, the bucket held the 10 photos under `persons/hamza_aziz/` and no job photos, and the roster showed `enrolled`.

## Not covered

- Encryption of the bucket with a key per client.
- Snapshots in `sites/<client>/snapshots/` and the owner's backups keep whoever they held: a snapshot older than 90 days may hold someone deleted since. A restore re-runs recorded deletions, but the files themselves are not pruned.
- Pictures saved to `Recognition_Frames/` when `SAVE_RECOGNITION_FRAMES` is on (off by default) are not cleared.
- Scope (owner, 2026-11-04, Face-Dataset-Collector D-025): only the owner's own face is enrolled. Enrolling anyone else waits for legal advice (legal basis, notice 1.2, the open end date for attendance records, controller or processor in central deployments) and for 8e on main, so deletion is automated first. Signed off: every re-enrolment records a new consent; a withdrawal during a re-enrolment ends only that attempt.
- Attendance records have no end date, and pictures on the records of people still enrolled are kept: both wait for legal advice.

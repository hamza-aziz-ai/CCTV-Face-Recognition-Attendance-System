# Bug: the ROI page could not start

**Symptom:** the `roi` image built and passed CI, but its Flask app failed on import, so the page never served.

**Root cause:** `Custom-ROI-Provisioning/app.py` imported `IP_CAMS` from `src/parameters.py` and `create_mask`, `roi_coordinates` from `src/util/generic_utilities.py`. All three were removed when cameras moved to `camera_configuration.json` with polygon `masking-coordinates`. The page also saved by rewriting `src/parameters.py` in place. CI only checked that `app.py` existed and that `cv2` and `numpy` imported, so it never noticed.

**Fix:** the page was rebuilt around the camera configuration (D-035), and CI now runs `Custom-ROI-Provisioning/test_app.py` in the image: it loads the page, lists cameras, serves a snapshot and a preview, saves one camera's region without touching the rest, refuses bad points, and clears a region.

**Lesson:** a smoke test that checks a file exists does not prove the app starts; import and call it.

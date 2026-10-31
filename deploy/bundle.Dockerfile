# The deployment bundle as an image, so hosts fetch it with the same registry login as the app images (D-033).
# It is never run: hosts copy the files out with docker create and docker cp. Built by release.yml from make_bundle.py.
FROM scratch
COPY . /bundle/
CMD ["none"]

# deepstream:9.1-hamza: one recipe for both machines
#   amd64: Windows laptop, Docker Desktop + WSL2, RTX 4050 (Ada, sm_89)
#   arm64: Jetson Orin Nano, JetPack 7.2.1 (L4T r39.2), Orin (sm_87)
#
# Build NATIVELY on each machine (do not cross-build: compiling OpenCV+CUDA for arm64
# under QEMU on the laptop would take many hours). The base tag is multi-arch, so
# Docker pulls the right build automatically.
#
#   Laptop (WSL bash, PowerShell or Git Bash), ~25-35 min:
#     docker build --build-arg MAKE_JOBS=8 -t deepstream:9.1-hamza .
#   Jetson (inside tmux; add a temporary 8 GB swap file first), ~65-75 min:
#     docker build -t deepstream:9.1-hamza .
#
# Then tag for the `ds` shortcut and protect it:
#   docker tag deepstream:9.1-hamza nvcr.io/nvidia/deepstream:9.1-triton-multiarch
#   docker create --name ds-keep --label purpose=protect-image deepstream:9.1-hamza true
#
# Note: NVIDIA's amd64 build of this tag is release 26.03 (TensorRT 10.16.0.72) and the
# arm64 build is release 26.04 (TensorRT 10.16.1.11). Build TensorRT engines on the
# machine (and in the image) that will run them.

FROM nvcr.io/nvidia/deepstream:9.1-triton-multiarch

# Set automatically by BuildKit (Docker 23+); used to choose per-arch defaults.
ARG TARGETARCH
# Empty = auto: 8.9 on amd64 (RTX 4050), 8.7 on arm64 (Orin). Override for other GPUs.
ARG CUDA_ARCH_BIN=
ARG MAKE_JOBS=4
ARG OPENCV_VERSION=4.14.0
ARG PYDS_COMMIT=8ad0349

ENV DEBIAN_FRONTEND=noninteractive
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# 1. NVIDIA add-on script: codec libraries for the libav/good/bad/ugly GStreamer plugins
#    and the patched rtpmanager (RTSP fix).
RUN cd /opt/nvidia/deepstream/deepstream && ./user_additional_install.sh

# 2. Tools, FFmpeg, Kafka client, kmod (lsmod, needed on Jetson), build dependencies for
#    pyds and OpenCV. Then reinstall libraries NVIDIA's image strips while leaving the
#    package marked installed (arm64: libswresample.so.4 missing, breaks libav + ffmpeg;
#    the others are from NVIDIA's own release notes). Harmless where nothing is missing.
RUN apt-get update && apt-get install -y --no-install-recommends \
        git vim nano wget curl unzip htop tmux kmod ffmpeg librdkafka-dev \
        build-essential pkg-config cmake meson ninja-build m4 autoconf automake libtool \
        python3-dev python3-venv python3-pip python3-build \
        python3-gi python3-gst-1.0 python-gi-dev libgirepository-2.0-dev libcairo2-dev \
        libglib2.0-dev libglib2.0-dev-bin libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev \
        libavcodec-dev libavformat-dev libswscale-dev libv4l-dev \
        libjpeg-dev libpng-dev libtiff-dev libwebp-dev libopenjp2-7-dev \
        libtbb-dev libeigen3-dev libopenblas-dev liblapack-dev liblapacke-dev && \
    apt-get install -y --reinstall libswresample4 libmp3lame0 libxvidcore4 && \
    rm -rf /var/lib/apt/lists/*

# 3. Disable the Rivermax UDP plugin (needs ConnectX + licensed Rivermax; only warns).
RUN P=/usr/lib/$(uname -m)-linux-gnu/gstreamer-1.0/deepstream/libnvdsgst_udp.so && \
    mkdir -p /opt/nvidia/deepstream/disabled-plugins && \
    if [ -f "$P" ]; then mv "$P" /opt/nvidia/deepstream/disabled-plugins/; fi

# 4. pyservicemaker ships preinstalled but misses pyyaml. NumPy pinned to 1.x
#    (OpenCV and pyds are built against the 1.x ABI).
RUN pip install --break-system-packages --no-cache-dir pyyaml "numpy==1.26.4"

# 5. pyds 1.2.3 from source at a pinned commit, built by hand (4 jobs, no throwaway venv).
#    DS 9.1 images keep headers in sources/includes; the extra include path covers
#    layouts like DS 9.2 on Jetson that use /opt/nvidia/deepstream/deepstream/includes.
#    The wheel is installed by absolute path from / (installing from inside bindings/
#    makes pip see pyds.egg-info and skip the install).
RUN cd /opt/nvidia/deepstream/deepstream/sources && \
    git clone https://github.com/NVIDIA-AI-IOT/deepstream_python_apps.git && \
    cd deepstream_python_apps && git checkout ${PYDS_COMMIT} && \
    git submodule update --init && \
    python3 bindings/3rdparty/git-partial-submodule/git-partial-submodule.py restore-sparse && \
    cd bindings && \
    export CMAKE_BUILD_PARALLEL_LEVEL=${MAKE_JOBS} && \
    export CMAKE_ARGS="-DCMAKE_CXX_FLAGS=-I/opt/nvidia/deepstream/deepstream/includes" && \
    python3 -m build && \
    cd / && pip install --break-system-packages --no-cache-dir \
        /opt/nvidia/deepstream/deepstream/sources/deepstream_python_apps/bindings/dist/pyds-*.whl \
        "cuda-python~=13.2.0" "numpy==1.26.4" && \
    rm -rf /opt/nvidia/deepstream/deepstream/sources/deepstream_python_apps/bindings/build /root/.cache

# 6. OpenCV 4.14 + contrib with CUDA (same flags as both verified builds; NVCUVID/NVENC
#    off). CUDA arch and cuDNN paths are chosen per architecture.
RUN ARCH_BIN="${CUDA_ARCH_BIN}"; \
    if [ -z "$ARCH_BIN" ]; then \
      if [ "${TARGETARCH:-$(dpkg --print-architecture)}" = "arm64" ]; then ARCH_BIN=8.7; else ARCH_BIN=8.9; fi; \
    fi; \
    MA=$(uname -m)-linux-gnu; \
    echo "Building OpenCV ${OPENCV_VERSION} for CUDA_ARCH_BIN=${ARCH_BIN} (${MA})" && \
    mkdir -p /opt/src && cd /opt/src && \
    git clone --depth 1 --branch ${OPENCV_VERSION} https://github.com/opencv/opencv.git && \
    git clone --depth 1 --branch ${OPENCV_VERSION} https://github.com/opencv/opencv_contrib.git && \
    mkdir opencv/build && cd opencv/build && \
    cmake .. \
      -D CMAKE_BUILD_TYPE=Release \
      -D CMAKE_INSTALL_PREFIX=/opt/opencv-4.14-cuda \
      -D CMAKE_INSTALL_RPATH="/opt/opencv-4.14-cuda/lib;/usr/local/cuda/lib64" \
      -D OPENCV_EXTRA_MODULES_PATH=/opt/src/opencv_contrib/modules \
      -D WITH_CUDA=ON -D ENABLE_CUDA_FIRST_CLASS_LANGUAGE=ON \
      -D CMAKE_CUDA_COMPILER=/usr/local/cuda/bin/nvcc -D CUDAToolkit_ROOT=/usr/local/cuda \
      -D CUDA_ARCH_BIN=${ARCH_BIN} -D CUDA_ARCH_PTX= \
      -D WITH_CUBLAS=ON -D WITH_CUFFT=ON -D WITH_CUDNN=ON -D OPENCV_DNN_CUDA=ON \
      -D CUDNN_INCLUDE_DIR=/usr/include/${MA} \
      -D CUDNN_LIBRARY=/usr/lib/${MA}/libcudnn.so \
      -D CUDA_FAST_MATH=ON -D WITH_NVCUVID=OFF -D WITH_NVCUVENC=OFF \
      -D WITH_GSTREAMER=ON -D WITH_V4L=ON -D WITH_FFMPEG=ON \
      -D WITH_GTK=OFF -D WITH_QT=OFF -D WITH_OPENGL=OFF \
      -D WITH_TBB=ON -D WITH_EIGEN=ON \
      -D BUILD_opencv_python3=ON -D PYTHON3_EXECUTABLE=/usr/bin/python3 \
      -D OPENCV_PYTHON3_INSTALL_PATH=lib/python3.12/site-packages \
      -D OPENCV_GENERATE_PKGCONFIG=ON -D OPENCV_ENABLE_NONFREE=OFF \
      -D BUILD_TESTS=OFF -D BUILD_PERF_TESTS=OFF -D BUILD_EXAMPLES=OFF \
      -D BUILD_DOCS=OFF -D BUILD_opencv_java=OFF && \
    make -j${MAKE_JOBS} && make install && \
    cd /opt/src && rm -rf opencv/build && \
    echo /opt/opencv-4.14-cuda/lib/python3.12/site-packages \
      > /usr/local/lib/python3.12/dist-packages/opencv-cuda.pth

# 7. Environment: OpenCV CLI / pkg-config / CMake discovery, and the sample `common`
#    helpers on PYTHONPATH (works in scripts too, not only interactive shells).
ENV PATH=/opt/opencv-4.14-cuda/bin:${PATH} \
    PKG_CONFIG_PATH=/opt/opencv-4.14-cuda/lib/pkgconfig \
    CMAKE_PREFIX_PATH=/opt/opencv-4.14-cuda \
    PYTHONPATH=/opt/nvidia/deepstream/deepstream/sources/deepstream_python_apps/apps

# 8. Build-time checks that need no GPU. GPU checks run after the build (see below).
RUN rm -rf /root/.cache/gstreamer-1.0 && \
    test -f /usr/local/lib/python3.12/dist-packages/pyds.so && echo "pyds.so installed" && \
    python3 -c "import yaml, numpy; print('pyyaml OK | numpy', numpy.__version__)" && \
    python3 -c "import cv2; l=[x for x in cv2.getBuildInformation().splitlines() if 'NVIDIA CUDA:' in x or 'NVIDIA GPU arch' in x]; assert l and 'YES' in l[0], l; print(cv2.__version__); [print(x.strip()) for x in l]" && \
    opencv_version && pkg-config --modversion opencv4 && \
    { ldd /usr/lib/$(uname -m)-linux-gnu/gstreamer-1.0/libgstlibav.so | grep "not found" && exit 1 || echo "libav libraries OK"; } && \
    ffmpeg -version | head -n1

WORKDIR /opt/nvidia/deepstream/deepstream

# After building, verify with the GPU (laptop: `ds` from WSL/PowerShell/Git Bash;
# Jetson: `ds`):
#   deepstream-app --version-all                          # no GStreamer warnings
#   python3 -c "import cv2, pyds; from pyservicemaker import Pipeline, Flow; print(cv2.cuda.getCudaEnabledDeviceCount())"   # 1
#   gst-launch-1.0 filesrc location=/opt/nvidia/deepstream/deepstream/samples/streams/sample_720p.mp4 ! qtdemux ! h264parse ! nvv4l2decoder ! fakesink

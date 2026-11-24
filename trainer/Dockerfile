# Entrenador de splats 3D (3D Gaussian Splatting con gsplat). Necesita GPU NVIDIA.
FROM nvidia/cuda:12.4.1-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    TORCH_CUDA_ARCH_LIST="8.6"

RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip python3-dev ninja-build \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install torch==2.4.1 --index-url https://download.pytorch.org/whl/cu124 \
    && pip3 install gsplat==1.5.3 pillow numpy packaging

COPY train.py /app/train.py
WORKDIR /app
CMD ["python3", "-u", "train.py"]

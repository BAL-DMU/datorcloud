# File: build/python-client/Dockerfile
FROM ubuntu:22.04

# Prevent interactive prompts during apt operations
ENV DEBIAN_FRONTEND=noninteractive

# 1. Install system dependencies needed for Miniconda installation
RUN apt-get update && apt-get install -y \
    wget \
    bzip2 \
    ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 2. Download and install Miniconda
#    This example uses the "latest" installer. You can pin a specific version if preferred.
RUN wget --progress=bar:force:noscroll \
    https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh \
    -O /tmp/miniconda.sh \
    && /bin/bash /tmp/miniconda.sh -b -p /opt/conda \
    && rm /tmp/miniconda.sh

# 3. Ensure conda is in PATH
ENV PATH="/opt/conda/bin:${PATH}"

# 4. Create a minimal environment and install Python 3.10 + data-science libraries
#    (Alternatively, you could use conda create -n env_name python=3.10 <packages>,
#     then conda activate it. Here, we install into the base environment for simplicity.)
RUN conda install -y \
    python=3.10 \
    pip \
    numpy \
    pandas \
    scikit-learn \
    matplotlib \
    && conda clean -ya

# 5. Set up your working directory
WORKDIR /app

# 6. Copy requirements if you still have Python packages to install via pip
COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# 7. Copy your application source code
COPY src/ /app/src/

# 8. Set the default working directory for your scripts
WORKDIR /app/src

# 9. Default command (override in docker-compose if needed)
CMD ["python", "--version"]

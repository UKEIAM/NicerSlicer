FROM mcr.microsoft.com/devcontainers/python:3.11

# Install the components required by Visual Studio Code given the script found at https://github.com/microsoft/vscode-dev-containers/tree/main/script-library.
# This is disabled by default. Set INSTALL_VSCODE = 1 to enable.
ARG INSTALL_VSCODE=0
ARG USERNAME=dev
ARG USER_UID=1000
ARG USER_GID=$USER_UID

# RUN if [ "${INSTALL_VSCODE}" = "1" ] ; \
#      then bash -c "$(curl -fsSL "https://raw.githubusercontent.com/microsoft/vscode-dev-containers/main/script-library/common-debian.sh")" -- "true" "${USERNAME}" "${USER_UID}" "${USER_GID}" "true" "true" "true"  && \
#      apt-get clean -y && rm -rf /var/lib/apt/lists/* && \
#      pip3 --disable-pip-version-check --no-cache-dir install ipykernel ipympl; \
#      else echo "Skipping VS Code" ; \
#     fi

# Install the (passwordless) SSH server
# Additionally, allow the user to call python directly
RUN if [ "${INSTALL_VSCODE}" = "0" ] ; \
    then apt-get update && apt-get install -y openssh-server && rm -rf /var/lib/apt/lists/* \
    mkdir /var/run/sshd && mkdir -p /run/sshd \
    echo 'root:root' | chpasswd && \
    useradd -m ${USERNAME} && passwd -d ${USERNAME} && \
    usermod -aG www-data ${USERNAME} && \
    sed -i'' -e's/^#PermitRootLogin prohibit-password$/PermitRootLogin yes/' /etc/ssh/sshd_config \
        && sed -i'' -e's/^#PasswordAuthentication yes$/PasswordAuthentication yes/' /etc/ssh/sshd_config \
        && sed -i'' -e's/^#PermitEmptyPasswords no$/PermitEmptyPasswords yes/' /etc/ssh/sshd_config \
        && sed -i'' -e's/^UsePAM yes/UsePAM no/' /etc/ssh/sshd_config && \
    echo 'export PATH="/opt/conda/bin:$PATH"' >> /home/${USERNAME}/.bashrc ; \
    else usermod -aG www-data vscode ; \
    fi

# Install poppler
RUN apt-get update && apt-get install poppler-utils -y

# Install the linters, black, and all the requirements in the requirements.txt
COPY requirements.txt /tmp/pip-tmp/
RUN pip3 --disable-pip-version-check --no-cache-dir install -r /tmp/pip-tmp/requirements.txt && rm -rf /tmp/pip-tmp

# Expose the SSH server
EXPOSE 22
CMD ["/usr/sbin/sshd", "-D"]
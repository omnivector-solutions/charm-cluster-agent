"""
ClusterAgentOps.
"""
import logging
import os
from pathlib import Path
import shlex
from shutil import copy2, rmtree
import subprocess


logger = logging.getLogger()


class ClusterAgentOps:
    """Track and perform cluster-agent ops."""

    _PACKAGE_NAME = "cluster-agent"
    _SYSTEMD_SERVICE_NAME = "cluster-agent"
    _LOG_DIR = Path("/var/log/cluster-agent")
    _SYSTEMD_BASE_PATH = Path("/usr/lib/systemd/system")
    _SYSTEMD_SERVICE_FILE = _SYSTEMD_BASE_PATH / f"{_PACKAGE_NAME}.service"
    _VENV_DIR = Path("/srv/cluster-agent-venv")
    _ENV_DEFAULTS = _VENV_DIR / ".env"
    _PIP_CMD = _VENV_DIR.joinpath("bin", "pip3.8").as_posix()
    _PYTHON_CMD = Path("/usr/bin/python3.8")

    CLUSTER_AGENT_USER = "cluster_agent"
    CLUSTER_AGENT_GROUP = CLUSTER_AGENT_USER
    CLUSTER_AGENT_USER_UID = "4671"

    def __init__(self, charm):
        """Initialize cluster-agent-ops."""
        self._charm = charm

    def _get_authorization_token(self):
        """Get authorization token for installing cluster-agent from CodeArtifact"""

        os.environ["AWS_ACCESS_KEY_ID"] = self._charm.model.config["aws-access-key-id"]
        os.environ["AWS_SECRET_ACCESS_KEY"] = self._charm.model.config[
            "aws-secret-access-key"
        ]

        domain = self._charm.model.config["package-url"].split("-")[0]

        import boto3

        sts = boto3.client("sts")
        session_token_payload = sts.get_session_token()

        os.environ["AWS_ACCESS_KEY_ID"] = session_token_payload.get("Credentials").get(
            "AccessKeyId"
        )
        os.environ["AWS_SECRET_ACCESS_KEY"] = session_token_payload.get(
            "Credentials"
        ).get("SecretAccessKey")
        os.environ["AWS_SESSION_TOKEN"] = session_token_payload.get("Credentials").get(
            "SessionToken"
        )
        os.environ["AWS_DEFAULT_REGION"] = self._charm.model.config["aws-region"]

        code_artifact = boto3.client("codeartifact")

        codeartifact_auth_token = code_artifact.get_authorization_token(domain=domain)
        return codeartifact_auth_token.get("authorizationToken")

    def _derived_package_url(self):
        """Derive the pypi package url from the the supplied config and package name."""
        package_url = self._charm.model.config["package-url"]
        authozation_token = self._get_authorization_token()
        pypi_url = f"https://aws:{authozation_token}@{package_url}"
        return pypi_url

    def install(self):
        """Install cluster-agent and setup ops."""
        # Create the cluster_agent user and group.
        self._create_cluster_agent_user_group()
        # Create and permission the cluster_agent log dir.
        self._create_and_permission_cluster_agent_log_dir()
        # Create the virtualenv and ensure pip is up to date.
        self._create_venv_and_ensure_latest_pip()
        # Install additional dependencies.
        self._install_extra_deps()
        # Install cluster-agent
        self._install_cluster_agent()
        # Provision the cluster-agent systemd service.
        self._setup_systemd()

    def upgrade(self, version: str):
        """Upgrade the cluster-agent python package."""
        self._upgrade_cluster_agent(version)

    def configure_env_defaults(self, ctxt):
        """Get the needed config, render and write out the file."""
        backend_url = ctxt.get("backend_url")
        log_dir = self._LOG_DIR.as_posix()
        username = self.CLUSTER_AGENT_USER
        auth0_domain = ctxt.get("auth0_domain")
        auth0_audience = ctxt.get("auth0_audience")
        auth0_client_id = ctxt.get("auth0_client_id")
        auth0_client_secret = ctxt.get("auth0_client_secret")

        ctxt = {
            "backend_url": backend_url,
            "log_dir": log_dir,
            "username": username,
            "auth0_domain": auth0_domain,
            "auth0_audience": auth0_audience,
            "auth0_client_id": auth0_client_id,
            "auth0_client_secret": auth0_client_secret,
        }

        env_template = Path(
            "./src/templates/cluster-agent.defaults.template"
        ).read_text()

        rendered_template = env_template.format(**ctxt)

        if self._ENV_DEFAULTS.exists():
            self._ENV_DEFAULTS.unlink()

        self._ENV_DEFAULTS.write_text(rendered_template)

    def systemctl(self, operation: str):
        """
        Run systemctl command.
        """
        cmd = [
            "systemctl",
            operation,
            self._SYSTEMD_SERVICE_NAME,
        ]
        try:
            subprocess.call(cmd)
        except subprocess.CalledProcessError as e:
            logger.error(f"Error running {' '.join(cmd)} - {e}")

    def remove(self):
        """
        Remove the things we have created.
        """
        # Stop and disable the systemd service.
        self.systemctl("stop")
        self.systemctl("disable")
        # Remove files and dirs created by this charm.
        if self._SYSTEMD_SERVICE_FILE.exists():
            self._SYSTEMD_SERVICE_FILE.unlink()
        subprocess.call(["systemctl", "daemon-reload"])
        rmtree(self._LOG_DIR.as_posix())
        rmtree(self._VENV_DIR.as_posix())
        # Delete the user and group
        subprocess.call(["userdel", self.CLUSTER_AGENT_USER])
        subprocess.call(["groupdel", self.CLUSTER_AGENT_GROUP])

    def _create_cluster_agent_user_group(self):
        logger.debug("## Creating the cluster_agent group")
        # use the UID as the GID too
        cmd = f"groupadd {self.CLUSTER_AGENT_GROUP} --gid {self.CLUSTER_AGENT_USER_UID}"
        try:
            subprocess.check_output(shlex.split(cmd))
        except subprocess.CalledProcessError as e:
            if e.returncode == 9:
                logger.debug("## Group already exists")
            else:
                logger.error(f"## Error creating cluster group: {e}")
                raise e

        logger.debug("## Creating cluster_agent user")
        cmd = (
            "useradd --system --no-create-home "
            f"--gid {self.CLUSTER_AGENT_GROUP} "
            "--shell /usr/sbin/nologin "
            f"-u {self.CLUSTER_AGENT_USER_UID} {self.CLUSTER_AGENT_USER}"
        )
        try:
            subprocess.check_output(shlex.split(cmd))
        except subprocess.CalledProcessError as e:
            if e.returncode == 9:
                logger.debug("## User already exists")
            else:
                logger.error(f"## Error creating cluster User: {e}")
                raise e

        logger.debug(f"## Adding cluster_agent user to {self._sudo_group} group")
        # Add the 'cluster_agent' user to sudo.
        # This is needed because the cluster_agent user need to create tokens for the root user.
        subprocess.call(
            shlex.split(f"usermod -aG {self._sudo_group} {self.CLUSTER_AGENT_USER}")
        )
        logger.debug(f"## cluster_agent user added to {self._sudo_group} group")

    @property
    def _sudo_group(self) -> str:
        os_release = Path("/etc/os-release").read_text().split("\n")
        os_release_ctxt = {
            k: v.strip('"')
            for k, v in [item.split("=") for item in os_release if item != ""]
        }

        # we need to take care of this corner case. All other OSes use "wheel"...
        if os_release_ctxt["ID"] == "ubuntu":
            return "sudo"

        return "wheel"

    def _create_and_permission_cluster_agent_log_dir(self):
        """Create the log dir and make sure it's owned by cluster_agent:cluster_agent."""
        if not self._LOG_DIR.exists():
            logger.debug(f"## Creating {self._LOG_DIR}")
            self._LOG_DIR.mkdir(parents=True)

        logger.debug(f"## Setting permissions for {self._LOG_DIR}")
        subprocess.call(
            [
                "chown",
                "-R",
                f"{self.CLUSTER_AGENT_USER}:{self.CLUSTER_AGENT_GROUP}",
                self._LOG_DIR.as_posix(),
            ]
        )
        logger.debug("## cluster-agent log dir created and permissioned")

    def _create_venv_and_ensure_latest_pip(self):
        """Create the virtualenv and upgrade pip."""

        # Create the virtualenv
        create_venv_cmd = [
            self._PYTHON_CMD,
            "-m",
            "venv",
            self._VENV_DIR.as_posix(),
        ]
        logger.debug(f"## Creating virtualenv: {create_venv_cmd }")
        subprocess.call(create_venv_cmd, env=dict())
        logger.debug("## cluster-agent virtualenv created")

        # Ensure we have the latest pip
        upgrade_pip_cmd = [
            self._PIP_CMD,
            "install",
            "--upgrade",
            "pip",
        ]
        logger.debug(f"## Updating pip: {upgrade_pip_cmd}")
        subprocess.call(upgrade_pip_cmd, env=dict())
        logger.debug("## Pip upgraded")

    def _setup_systemd(self):
        """Provision the cluster-agent systemd service."""
        logger.debug(f"## Setting SystemD service: {self._SYSTEMD_SERVICE_FILE}")
        if self._SYSTEMD_SERVICE_FILE.exists():
            self._SYSTEMD_SERVICE_FILE.unlink()
        copy2(
            "./src/templates/cluster-agent.service",
            self._SYSTEMD_SERVICE_FILE.as_posix(),
        )
        logger.debug("## Enabling Cluster service")
        self.systemctl("enable")
        logger.debug("## Cluster service enabled")

    def _install_extra_deps(self):
        """Install additional dependencies."""
        # Install uvicorn and pyyaml
        cmd = [self._PIP_CMD, "install", "uvicorn", "pyyaml", "boto3==1.18.55"]
        logger.debug(f"## Installing exra dependencies: {cmd}")
        try:
            subprocess.call(cmd, env=dict())
        except subprocess.CalledProcessError as e:
            logger.error(f"Error running {' '.join(cmd)} - {e}")
            raise e

    def _install_cluster_agent(self):
        """Install the cluster-agent package."""
        cmd = [
            self._PIP_CMD,
            "install",
            "--use-deprecated",
            "html5lib",
            "-U",
            "-i",
            self._derived_package_url(),
            self._PACKAGE_NAME,
        ]
        subprocess.call("echo {}".format(cmd).split())
        logger.debug(f"## Installing cluster: {cmd}")
        try:
            subprocess.call(cmd, env=dict())
        except subprocess.CalledProcessError as e:
            logger.error(f"Error running {' '.join(cmd)} - {e}")
            raise e

    def _upgrade_cluster_agent(self, version: str):
        """Upgrade the cluster-agent python package."""
        cmd = [
            self._PIP_CMD,
            "install",
            "-U",
            "-i",
            self._derived_package_url(),
            f"{self._PACKAGE_NAME}=={version}",
        ]

        try:
            subprocess.call(cmd, env=dict())
        except subprocess.CalledProcessError as e:
            logger.error(f"Error running {' '.join(cmd)} - {e}")
            raise e

    def start_agent(self):
        """Starts the cluster-agent"""
        self.systemctl("start")

    def stop_agent(self):
        """Stops the cluster-agent"""
        self.systemctl("stop")

    def restart_agent(self):
        """Restars the cluster-agent"""
        self.systemctl("restart")

"""
ClusterAgentOps.
"""
import logging
import shlex
import subprocess
from pathlib import Path
from shutil import copy2, rmtree
from typing import Dict, Any

from jinja2 import Environment, FileSystemLoader


logger = logging.getLogger()


class ClusterAgentOps:
    """Track and perform cluster-agent ops."""

    _PACKAGE_NAME = "cluster-agent"
    _SYSTEMD_SERVICE_NAME = "cluster-agent"
    _SYSTEMD_BASE_PATH = Path("/usr/lib/systemd/system")
    _SYSTEMD_SERVICE_FILE = _SYSTEMD_BASE_PATH / f"{_PACKAGE_NAME}.service"
    _SYSTEMD_TIMER_NAME = f"{_PACKAGE_NAME}.timer"
    _SYSTEMD_TIMER_FILE = _SYSTEMD_BASE_PATH / _SYSTEMD_TIMER_NAME
    _VENV_DIR = Path("/srv/cluster-agent-venv")
    _ENV_DEFAULTS = _VENV_DIR / ".env"
    _PIP_CMD = _VENV_DIR.joinpath("bin", "pip3.8").as_posix()
    _PYTHON_CMD = Path("/usr/bin/python3.8")

    def __init__(self, charm):
        """Initialize cluster-agent-ops."""
        self._charm = charm

    def _get_authorization_token(self):
        """Get authorization token for installing cluster-agent from CodeArtifact"""

        domain = self._charm.model.config["package-url"].split("-")[0]

        import boto3

        sts = boto3.client(
            "sts",
            aws_access_key_id=self._charm.model.config["aws-access-key-id"],
            aws_secret_access_key=self._charm.model.config["aws-secret-access-key"]
        )
        session_token_payload = sts.get_session_token()

        code_artifact = boto3.client(
            "codeartifact",
            aws_access_key_id=session_token_payload.get("Credentials").get("AccessKeyId"),
            aws_secret_access_key=session_token_payload.get("Credentials").get("SecretAccessKey"),
            aws_session_token=session_token_payload.get("Credentials").get("SessionToken"),
            region_name=self._charm.model.config["aws-region"],
        )

        codeartifact_auth_token = code_artifact.get_authorization_token(domain=domain)
        return codeartifact_auth_token.get("authorizationToken")

    def _derived_package_url(self):
        """Derive the pypi package url from the the supplied config and package name."""
        package_url = self._charm.model.config["package-url"]
        authorization_token = self._get_authorization_token()
        pypi_url = f"https://aws:{authorization_token}@{package_url}"
        return pypi_url

    def install(self):
        """Install cluster-agent and setup ops."""
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

    def configure_env_defaults(self, config_context: Dict[str, Any]):
        """
        Map charm configs found in the config_context to app settings.

        Map the settings found in the charm's config.yaml to the expected
        settings for the application (including the prefix). Write all settings to the
        configured dot-env file. If the file exists, it should be replaced.
        """
        prefix = "CLUSTER_AGENT_"
        with open(self._ENV_DEFAULTS, 'w') as env_file:
            for (key, value) in config_context.items():
                mapped_key = key.replace('-', '_').upper()
                print(f"{prefix}{mapped_key}={value}", file=env_file)

    def systemctl(self, operation: str):
        """
        Run systemctl operation for the service.
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
        if self._SYSTEMD_TIMER_FILE.exists():
            self._SYSTEMD_TIMER_FILE.unlink()
        subprocess.call(["systemctl", "daemon-reload"])
        rmtree(self._VENV_DIR.as_posix())

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
        copy2(
            "./src/templates/cluster-agent.service",
            self._SYSTEMD_SERVICE_FILE.as_posix(),
        )

        charm_config = self._charm.model.config
        stat_interval = charm_config.get("stat-interval")
        ctxt = {"stat_interval": stat_interval}

        template_dir = Path("./src/templates/")
        environment = Environment(loader=FileSystemLoader(template_dir))
        template = environment.get_template(self._SYSTEMD_TIMER_NAME)

        rendered_template = template.render(ctxt)
        self._SYSTEMD_TIMER_FILE.write_text(rendered_template)

        subprocess.call(["systemctl", "daemon-reload"])
        subprocess.call(["systemctl", "enable", "--now", "cluster-agent.timer"])

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

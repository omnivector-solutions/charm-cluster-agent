"""
ClusterAgentOps.
"""
import logging
import subprocess
from pathlib import Path
from shutil import copy2, rmtree
from typing import Dict, Any

from jinja2 import Environment, FileSystemLoader


logger = logging.getLogger()


class ClusterAgentOps:
    """Track and perform cluster-agent ops."""

    _PACKAGE_NAME = "ovs-cluster-agent"
    _SYSTEMD_SERVICE_NAME = "ovs-cluster-agent"
    _SYSTEMD_BASE_PATH = Path("/usr/lib/systemd/system")
    _SYSTEMD_SERVICE_FILE = _SYSTEMD_BASE_PATH / f"{_PACKAGE_NAME}.service"
    _SYSTEMD_TIMER_NAME = f"{_PACKAGE_NAME}.timer"
    _SYSTEMD_TIMER_FILE = _SYSTEMD_BASE_PATH / _SYSTEMD_TIMER_NAME
    _VENV_DIR = Path("/srv/ovs-cluster-agent-venv")
    _ENV_DEFAULTS = _VENV_DIR / ".env"
    _PIP_CMD = _VENV_DIR.joinpath("bin", "pip3.8").as_posix()
    _PYTHON_CMD = Path("/usr/bin/python3.8")
    _CACHE_DIR = Path("/var/cache/cluster-agent")

    def __init__(self, charm):
        """Initialize cluster-agent-ops."""
        self._charm = charm

    def install(self):
        """Install cluster-agent and setup ops."""
        # Create the virtualenv and ensure pip is up to date.
        self._create_venv_and_ensure_latest_pip()
        # Install additional dependencies.
        self._install_extra_deps()
        # Install cluster-agent
        self._install_cluster_agent()
        # Clear cached data
        self._clear_cache_dir()
        # Provision the cluster-agent systemd service.
        self._setup_systemd()

    def upgrade(self, version: str):
        """Upgrade the cluster-agent python package."""
        # Clear cached data
        self._clear_cache_dir()
        self._upgrade_cluster_agent(version)

    def configure_env_defaults(self, config_context: Dict[str, Any]):
        """
        Map charm configs found in the config_context to app settings.

        Map the settings found in the charm's config.yaml to the expected
        settings for the application (including the prefix). Write all settings to the
        configured dot-env file. If the file exists, it should be replaced.
        """
        prefix = "CLUSTER_AGENT_"
        with open(self._ENV_DEFAULTS, "w") as env_file:
            for (key, value) in config_context.items():
                mapped_key = key.replace("-", "_").upper()
                print(f"{prefix}{mapped_key}={value}", file=env_file)

            print(f"{prefix}CACHE_DIR={self._CACHE_DIR}", file=env_file)

        # Clear cached data
        self._clear_cache_dir()

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
            "./src/templates/ovs-cluster-agent.service",
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
        subprocess.call(["systemctl", "enable", "--now", self._SYSTEMD_TIMER_NAME])

    def _install_extra_deps(self):
        """Install additional dependencies."""
        # Install uvicorn and pyyaml
        cmd = [self._PIP_CMD, "install", "uvicorn", "pyyaml"]
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
            "-U",
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
            f"{self._PACKAGE_NAME}=={version}",
        ]

        try:
            subprocess.call(cmd, env=dict())
        except subprocess.CalledProcessError as e:
            logger.error(f"Error running {' '.join(cmd)} - {e}")
            raise e

    def _clear_cache_dir(self):
        """Clear the cache dir. Cluster-agent will recreate it on the next run."""

        if self._CACHE_DIR.exists():
            logger.debug(f"Clearing cache dir {self._CACHE_DIR.as_posix()}")
            rmtree(self._CACHE_DIR, ignore_errors=True)
        else:
            logger.debug(
                "Tried to clean cache dir {}, but it does not exist".format(
                    self._CACHE_DIR.as_posix()
                )
            )

    def start_agent(self):
        """Starts the cluster-agent"""
        self.systemctl("start")

    def stop_agent(self):
        """Stops the cluster-agent"""
        self.systemctl("stop")

    def restart_agent(self):
        """Restars the cluster-agent"""
        self.systemctl("restart")

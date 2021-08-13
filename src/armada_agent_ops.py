"""
ArmadaAgentOps.
"""
import logging
import shlex
import subprocess

from shutil import rmtree, copy2

from pathlib import Path


logger = logging.getLogger()


class ArmadaAgentOps:
    """Track and perform armada-agent ops."""

    _PACKAGE_NAME = "armada-agent"
    _SYSTEMD_SERVICE_NAME = "armada-agent"
    _LOG_DIR = Path("/var/log/armada-agent")
    _SYSTEMD_BASE_PATH = Path("/usr/lib/systemd/system")
    _SYSTEMD_SERVICE_FILE = _SYSTEMD_BASE_PATH / f"{_PACKAGE_NAME}.service"
    _VENV_DIR = Path("/srv/armada-agent-venv")
    _ENV_DEFAULTS = _VENV_DIR / ".env"
    _PIP_CMD = _VENV_DIR.joinpath("bin", "pip3").as_posix()

    _ARMADA_AGENT_USER = "armada_agent"
    _ARMADA_AGENT_GROUP = _ARMADA_AGENT_USER

    def __init__(self, charm):
        """Initialize armada-agent-ops."""
        self._charm = charm

    def _derived_pypi_url(self):
        """Derive the pypi package url from the the supplied config and package name."""
        url = self._charm.model.config["pypi-url"]
        url = url.split("://")[1]
        pypi_username = self._charm.model.config["pypi-username"]
        pypi_password = self._charm.model.config["pypi-password"]
        return (f"https://{pypi_username}:{pypi_password}@"
                f"{url}/simple/{self._PACKAGE_NAME}")

    def install(self):
        """Install armada-agent and setup ops."""
        # Create the armada_agent user and group.
        self._create_armada_agent_user_group()
        # Create and permission the armada_agent log dir.
        self._create_and_permission_armada_agent_log_dir()
        # Create the virtualenv and ensure pip is up to date.
        self._create_venv_and_ensure_latest_pip()
        # Install armada-agent
        self._install_armada_agent()
        # Install additional dependencies.
        self._install_extra_deps()
        # Provision the armada-agent systemd service.
        self._setup_systemd()

    def upgrade(self, version: str):
        """Upgrade the armada-agent python package."""
        self._upgrade_armada_agent(version)

    def configure_env_defaults(self, ctxt):
        """Get the needed config, render and write out the file."""
        api_key = ctxt.get("api_key")
        backend_url = ctxt.get("backend_url")
        log_dir = self._LOG_DIR.as_posix()
        username = "root"

        ctxt = {
            "backend_url": backend_url,
            "api_key": api_key,
            "log_dir": log_dir,
            "username": username
        }

        env_template = Path(
            "./src/templates/armada-agent.defaults.template").read_text()

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
        subprocess.call(["userdel", self._ARMADA_USER])
        subprocess.call(["groupdel", self._ARMADA_GROUP])

    def _create_armada_agent_user_group(self):
        logger.debug("## Creating the armada_agent group")
        cmd = f"groupadd {self._ARMADA_GROUP}"
        subprocess.call(shlex.split(cmd))

        logger.debug("## Creating armada_agent user")
        cmd = (
            "useradd --system --no-create-home "
            f"--gid {self._ARMADA_GROUP} --shell /usr/sbin/nologin {self._ARMADA_USER}"
        )
        subprocess.call(shlex.split(cmd))
        # Add the 'armada_agent' user to sudo.
        # This is needed because the armada_agent user need to create tokens for the root user.
        subprocess.call(shlex.split(f"usermod -aG sudo {self.ARMADA_USER}"))

    def _create_and_permission_armada_agent_log_dir(self):
        """Create the log dir and make sure it's owned by armada_agent:armada_agent."""
        if not self._LOG_DIR.exists():
            self._LOG_DIR.mkdir(parents=True)
        subprocess.call(
            [
                "chown",
                "-R",
                f"{self._ARMADA_USER}:{self._ARMADA_GROUP}",
                self._LOG_DIR.as_posix()
            ]
        )
        logger.debug("armada-agent log dir created and permissioned.")

    def _create_venv_and_ensure_latest_pip(self):
        """Create the virtualenv and upgrade pip."""

        # Create the virtualenv
        create_venv_cmd = [
            "python3",
            "-m",
            "venv",
            self._VENV_DIR.as_posix(),
        ]
        subprocess.call(create_venv_cmd)
        logger.debug("armada-agent virtualenv created")

        # Ensure we have the latest pip
        upgrade_pip_cmd = [
            self._PIP_CMD,
            "install",
            "--upgrade",
            "pip",
        ]
        subprocess.call(upgrade_pip_cmd)

    def _setup_systemd(self):
        """Provision the armada-agent systemd service."""
        # Copy the service file.
        if self._SYSTEMD_SERVICE_FILE.exists():
            self._SYSTEMD_SERVICE_FILE.unlink()
        copy2(
            "./src/templates/armada-agent.service",
            self._SYSTEMD_SERVICE_FILE.as_posix()
        )
        # Enable the systemd service.
        self.systemctl("enable")

    def _install_extra_deps(self):
        """Install additional dependencies."""
        # Install uvicorn and pyyaml
        cmd = [self._PIP_CMD, "install", "uvicorn", "pyyaml"]
        try:
            subprocess.call(cmd)
        except subprocess.CalledProcessError as e:
            logger.error(f"Error running {' '.join(cmd)} - {e}")
            raise e

    def _install_armada_agent(self):
        """Install the armada-agent package."""
        cmd = [self._PIP_CMD, "install", "-f", self._derived_pypi_url(), self._PACKAGE_NAME]
        try:
            subprocess.call([shlex.quote(item) for item in cmd])
        except subprocess.CalledProcessError as e:
            logger.error(f"Error running {' '.join(cmd)} - {e}")
            raise e

    def _upgrade_armada_agent(self, version: str):
        """Upgrade the armada-agent python package."""
        cmd = [
            self._PIP_CMD,
            "install",
            "--upgrade",
            "-f",
            f"{self._derived_pypi_url()}=={version}",
        ]

        try:
            subprocess.call([shlex.quote(item) for item in cmd])
        except subprocess.CalledProcessError as e:
            logger.error(f"Error running {' '.join(cmd)} - {e}")
            raise e

"""
ArmadaAgentOps.
"""
import logging
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

        # Create log dir
        if not self._LOG_DIR.exists():
            self._LOG_DIR.mkdir(parents=True)

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

        # Install uvicorn and pyyaml
        pip_install_pyyaml_uvicorn = [
            self._PIP_CMD,
            "install",
            "uvicorn",
            "pyyaml",
        ]
        subprocess.check_output(
            pip_install_pyyaml_uvicorn).decode().strip()

        # Install armada-agent
        pip_install_cmd = [
            self._PIP_CMD,
            "install",
            "-f",
            self._derived_pypi_url(),
            self._PACKAGE_NAME,
        ]
        subprocess.check_output(pip_install_cmd).decode().strip()

        # Setup systemd service file
        copy2(
            "./src/templates/armada-agent.service",
            self._SYSTEMD_SERVICE_FILE.as_posix()
        )

        # Enable the systemd service
        self.systemctl("enable")

    def upgrade(self, version: str):
        """Upgrade armada-agent."""
        pip_install_cmd = [
            self._PIP_CMD,
            "install",
            "--upgrade",
            "-f",
            f"{self._derived_pypi_url()}=={version}",
        ]

        subprocess.check_output(pip_install_cmd).decode().strip()

    def configure_env_defaults(self, ctxt):
        """Get the needed config, render and write out the file."""
        api_key = ctxt.get("api_key")
        base_api_url = ctxt.get("base_api_url")
        log_dir = self._LOG_DIR.as_posix()
        username = "root"

        ctxt = {
            "base_api_url": base_api_url,
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
        self.systemctl("stop")
        self.systemctl("disable")
        if self._SYSTEMD_SERVICE_FILE.exists():
            self._SYSTEMD_SERVICE_FILE.unlink()
        subprocess.call(["systemctl", "daemon-reload"])
        rmtree(self._LOG_DIR.as_posix())
        rmtree(self._VENV_DIR.as_posix())

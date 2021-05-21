"""
ArmadaAgentOps.
"""
import logging
import subprocess

from shutil import rmtree

from pathlib import Path


logger = logging.getLogger()


class ArmadaAgentOps:
    """Track and perform armada-agent ops."""

    _ARMADA_AGENT_PACKAGE_NAME = "armada-agent"
    _SYSTEMD_SERVICE_NAME = "armada-agent"
    _LOG_DIR = Path("/var/log/armada-agent")
    _ETC_DEFAULT = Path("/etc/default/armada-agent")
    _SYSTEMD_BASE_PATH = Path("/usr/lib/systemd/system")
    _VENV_DIR = Path("/srv/armada-agent-venv")
    _PIP_CMD = _VENV_DIR.joinpath("bin", "pip3").as_posix()

    def __init__(self, charm):
        """Initialize armada-agent-ops."""
        self._charm = charm

    def install(self):
        """Install armada-agent and setup ops."""
        pypi_url = self._charm.model.config["pypi-url"]
        pypi_username = self._charm.model.config["pypi-username"]
        pypi_password = self._charm.model.config["pypi-password"]

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

        # Install PyYAML
        subprocess.call(["./src/templates/install_pyyaml.sh"])

        # Install armada-agent
        url = pypi_url.split("://")[1]
        pip_install_cmd = [
            self._PIP_CMD,
            "install",
            "-f",
            f"https://{pypi_username}:{pypi_password}@{url}",
            self._ARMADA_AGENT_PACKAGE_NAME,
        ]
        out = subprocess.check_output(pip_install_cmd).decode().strip()
        if "Successfully installed" not in out:
            logger.error("Trouble installing armada-agent, please debug")
        else:
            logger.debug("armada-agent installed")

    def upgrade(self, version: str):
        """Upgrade armada-agent."""
        pypi_url = self._charm.model.config["pypi-url"]
        pypi_username = self._charm.model.config["pypi-username"]
        pypi_password = self._charm.model.config["pypi-password"]

        url = pypi_url.split("://")[1]
        pip_install_cmd = [
            self._PIP_CMD,
            "install",
            "--upgrade",
            "-f",
            f"https://{pypi_username}:{pypi_password}@{url}",
            f"{self._ARMADA_AGENT_PACKAGE_NAME}=={version}",
        ]

        out = subprocess.check_output(pip_install_cmd).decode().strip()
        if "Successfully installed" not in out:
            logger.error("Trouble upgrading armada-agent, please debug")
        else:
            logger.debug("armada-agent installed")

    def configure_etc_default(self):
        """Get the needed config, render and write out the file."""
        charm_config = self._charm.model.config
        jwt = charm_config.get("jwt")
        api_key = charm_config.get("api-key")
        backend_url = charm_config.get("backend-url")

        log_base_dir = str(self._LOG_DIR)

        ctxt = {
            "backend_url": backend_url,
            "jwt": jwt,
            "api_key": api_key,
            "log_dir": log_base_dir,
        }

        etc_default_template = Path(
            "./src/templates/armada-agent.defaults.template").read_text()

        rendered_template = etc_default_template.format(**ctxt)

        if self._ETC_DEFAULT.exists():
            self._ETC_DEFAULT.unlink()

        self._ETC_DEFAULT.write_text(rendered_template)

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
        self._ETC_DEFAULT.unlink()
        rmtree(self._LOG_DIR.as_posix())
        rmtree(self._VENV_DIR.as_posix())

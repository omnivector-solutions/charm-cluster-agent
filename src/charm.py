#!/usr/bin/env python3
"""ArmadaAgentCharm."""
import logging

from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import BlockedStatus, WaitingStatus, ActiveStatus

from armada_agent_ops import ArmadaAgentOps
from interface_user_group import UserGroupProvides


logger = logging.getLogger()


class ArmadaAgentCharm(CharmBase):
    """Facilitate Armada-agent lifecycle."""

    stored = StoredState()

    def __init__(self, *args):
        """Initialize and observe."""
        super().__init__(*args)

        self.stored.set_default(installed=False)
        self.stored.set_default(api_key=str())
        self.stored.set_default(backend_url=str())
        self.stored.set_default(config_available=False)
        self.stored.set_default(user_created=False)

        self.armada_agent_ops = ArmadaAgentOps(self)
        self._user_group = UserGroupProvides(self, "user-group")

        event_handler_bindings = {
            self.on.install: self._on_install,
            self.on.start: self._on_start,
            self.on.config_changed: self._on_config_changed,
            self.on.remove: self._on_remove,
            self.on.upgrade_action: self._on_upgrade_action,
        }
        for event, handler in event_handler_bindings.items():
            self.framework.observe(event, handler)

    def _on_install(self, event):
        """Install armada-agent."""
        try:
            self.armada_agent_ops.install()
            self.stored.installed = True
        except:
            self.stored.installed = False
            self.unit.status = BlockedStatus("Error installing armada-agent")
            event.defer()
            return
        # Log and set status
        logger.debug("armada-agent installed")
        self.unit.status = WaitingStatus("armada-agent installed")

    def _on_start(self, event):
        """
        Start armada-agent.

        Check that we have the needed configuration values and whether the
        armada agent user is created in the slurmctld node, if so
        start the armada-agent otherwise defer the event.
        """
        if not self.stored.config_available:
            event.defer()
            return

        if not self.stored.user_created:
            self.unit.status = WaitingStatus("waiting relation with slurmctld")
            event.defer()
            return

        logger.info("## Starting Armada agent")
        self.armada_agent_ops.systemctl("start")
        self.unit.status = ActiveStatus("armada agent started")

    def _on_config_changed(self, event):
        """Configure armada-agent."""

        # Get the api-key from the charm config
        api_key_from_config = self.model.config.get("api-key")
        if api_key_from_config != self.stored.api_key:
            self.stored.api_key = api_key_from_config

        # Get the backend-url from the charm config
        backend_url_from_config = self.model.config.get("backend-url")
        if backend_url_from_config != self.stored.backend_url:
            self.stored.backend_url = backend_url_from_config

        if not all([api_key_from_config, backend_url_from_config]):
            event.defer()
            return

        ctxt = {
            "api_key": api_key_from_config,
            "backend_url": backend_url_from_config,
        }

        self.armada_agent_ops.configure_env_defaults(ctxt)
        self.stored.config_available = True

    def _on_remove(self, event):
        """Remove directories and files created by armada-agent charm."""
        self.armada_agent_ops.remove()

    def _on_upgrade_action(self, event):
        version = event.params["version"]
        try:
            self.armada_agent_ops.upgrade(version)
            event.set_results({"upgrade": "success"})
        except:
            self.unit.status = BlockedStatus("Error upgrading armada-agent")
            event.fail(message="Error upgrading armada-agent")
            event.defer()


if __name__ == "__main__":
    main(ArmadaAgentCharm)

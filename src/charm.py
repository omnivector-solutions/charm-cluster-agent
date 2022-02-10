#!/usr/bin/env python3
"""ClusterAgentCharm."""
import logging

from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus

from cluster_agent_ops import ClusterAgentOps
from interface_user_group import UserGroupRequires


logger = logging.getLogger()


class ClusterAgentCharm(CharmBase):
    """Facilitate Cluster-agent lifecycle."""

    stored = StoredState()

    def __init__(self, *args):
        """Initialize and observe."""
        super().__init__(*args)

        self.stored.set_default(installed=False)
        self.stored.set_default(backend_url=str())
        self.stored.set_default(auth0_domain=str())
        self.stored.set_default(auth0_audience=str())
        self.stored.set_default(auth0_client_id=str())
        self.stored.set_default(auth0_client_secret=str())
        self.stored.set_default(config_available=False)
        self.stored.set_default(user_created=False)

        self.cluster_agent_ops = ClusterAgentOps(self)
        self._user_group = UserGroupRequires(self, "user-group")

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
        """Install cluster-agent."""
        try:
            self.cluster_agent_ops.install()
            self.stored.installed = True
        except Exception as e:
            logger.error(f"## Error installing agent: {e}")
            self.stored.installed = False
            self.unit.status = BlockedStatus("Error installing cluster-agent")
            event.defer()
            return
        # Log and set status
        logger.debug("cluster-agent installed")
        self.unit.status = WaitingStatus("cluster-agent installed")

    def _on_start(self, event):
        """
        Start cluster-agent.

        Check that we have the needed configuration values and whether the
        cluster agent user is created in the slurmctld node, if so
        start the cluster-agent otherwise defer the event.
        """
        if not self.stored.config_available:
            event.defer()
            return

        if not self.stored.user_created:
            self.unit.status = WaitingStatus("waiting relation with slurmctld")
            event.defer()
            return

        logger.info("## Starting Cluster agent")
        self.cluster_agent_ops.start_agent()
        self.unit.status = ActiveStatus("cluster agent started")

    def _on_config_changed(self, event):
        """Configure cluster-agent."""

        # Get the Auth0 domain from the charm config
        auth0_domain_from_config = self.model.config.get("auth0-domain")
        if auth0_domain_from_config != self.stored.auth0_domain:
            self.stored.auth0_domain = auth0_domain_from_config

        # Get the Auth0 audience from the charm config
        auth0_audience_from_config = self.model.config.get("auth0-audience")
        if auth0_audience_from_config != self.stored.auth0_audience:
            self.stored.auth0_audience = auth0_audience_from_config

        # Get the Auth0 client ID from the charm config
        auth0_client_id_from_config = self.model.config.get("auth0-client-id")
        if auth0_client_id_from_config != self.stored.auth0_client_id:
            self.stored.auth0_client_id = auth0_client_id_from_config

        # Get the Auth0 client secret from the charm config
        auth0_client_secret_from_config = self.model.config.get("auth0-client-secret")
        if auth0_client_secret_from_config != self.stored.auth0_client_secret:
            self.stored.auth0_client_secret = auth0_client_secret_from_config

        # Get the backend-url from the charm config
        backend_url_from_config = self.model.config.get("backend-url")
        if backend_url_from_config != self.stored.backend_url:
            self.stored.backend_url = backend_url_from_config

        if not all(
            [
                auth0_domain_from_config,
                auth0_audience_from_config,
                auth0_client_id_from_config,
                auth0_client_secret_from_config,
                backend_url_from_config,
            ]
        ):
            event.defer()
            return

        ctxt = {
            "backend_url": backend_url_from_config,
            "auth0_domain": auth0_domain_from_config,
            "auth0_audience": auth0_audience_from_config,
            "auth0_client_id": auth0_client_id_from_config,
            "auth0_client_secret": auth0_client_secret_from_config,
        }

        self.cluster_agent_ops.configure_env_defaults(ctxt)
        self.stored.config_available = True

    def _on_remove(self, event):
        """Remove directories and files created by cluster-agent charm."""
        self.cluster_agent_ops.remove()

    def _on_upgrade_action(self, event):
        version = event.params["version"]
        try:
            self.cluster_agent_ops.upgrade(version)
            event.set_results({"upgrade": "success"})
            self.cluster_agent_ops.restart_agent()
        except:
            self.unit.status = BlockedStatus("Error upgrading cluster-agent")
            event.fail(message="Error upgrading cluster-agent")
            event.defer()


if __name__ == "__main__":
    main(ClusterAgentCharm)

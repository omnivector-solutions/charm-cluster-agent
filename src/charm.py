#!/usr/bin/env python3
"""ClusterAgentCharm."""
import logging

from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus

from cluster_agent_ops import ClusterAgentOps


logger = logging.getLogger()

# Create a sentinel value. For more information about sentinel values and their
# purpose, see the PEP (with some excellent examples and rationale) here:
# https://peps.python.org/pep-0661/
unset = object()


class ClusterAgentCharm(CharmBase):
    """Facilitate Cluster-agent lifecycle."""

    stored = StoredState()

    def __init__(self, *args):
        """Initialize and observe."""
        super().__init__(*args)

        self.stored.set_default(installed=False)
        self.stored.set_default(config_available=False)
        self.stored.set_default(user_created=False)

        self.cluster_agent_ops = ClusterAgentOps(self)

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

        logger.info("## Starting Cluster agent")
        self.cluster_agent_ops.start_agent()
        self.unit.status = ActiveStatus("cluster agent started")

    def _on_config_changed(self, event):
        """
        Handle changes to the charm config.

        If all the needed settings are available in the charm config, create the
        environment settings for the charmed app. Also, store the config values in the
        stored state for the charm.

        Note the use of the sentinel ``unset`` value here. This allows us to
        distinguish between *unset* values and values that were *explicitly* set to
        falsey or null values. For more information about sentinel values, see
        `PEP-661 <https://peps.python.org/pep-0661/>_`.
        """

        settings_to_map = {
            "base-api-url": True,
            "base-slurmrestd-url": True,
            "cache-dir": True,
            "sentry-dsn": False,
            "auth0-domain": True,
            "auth0-audience": True,
            "auth0-client-id": True,
            "auth0-client-secret": True,
            "ldap-domain": False,
            "ldap-username": False,
            "ldap-password": False,
            "ldap-auth-type": False,
            "x-slurm-user-name": True,
        }

        env_context = dict()

        for (setting, is_required) in settings_to_map.items():
            value = self.model.config.get(setting, unset)

            # If any config value is not yet available, defer
            if value is unset:
                if is_required:
                    event.defer()
                    return
            else:
                env_context[setting] = value

                mapped_key = setting.replace("-", "_")
                store_value = getattr(self.stored, mapped_key, unset)
                if store_value != value:
                    setattr(self.stored, mapped_key, value)

        self.cluster_agent_ops.configure_env_defaults(env_context)
        self.stored.config_available = True

        logger.info("## Restarting Cluster agent")
        self.cluster_agent_ops.restart_agent()
        self.unit.status = ActiveStatus("cluster agent restarted")

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

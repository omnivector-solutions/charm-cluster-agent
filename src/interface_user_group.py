import logging

from ops.framework import Object
from ops.model import ActiveStatus, WaitingStatus


logger = logging.getLogger()


class UserGroupProvides(Object):
    def __init__(self, charm, relation_name):
        """Observe relation events."""
        super().__init__(charm, relation_name)
        self._charm = charm
        self._relation_name = relation_name

        self.framework.observe(
            self._charm.on[self._relation_name].relation_created,
            self._on_relation_created,
        )
        self.framework.observe(
            self._charm.on[self._relation_name].relation_changed,
            self._on_relation_changed,
        )
        self.framework.observe(
            self._charm.on[self._relation_name].relation_broken,
            self._on_relation_broken,
        )

    @property
    def _relation(self):
        return self.framework.model.get_relation(self._relation_name)

    def _on_relation_created(self, event):
        """Create the user and group sent by the provides side of the relation."""
        self._relation.data[self.model.app]["user"] = "armada_agent"
        self._relation.data[self.model.app]["group"] = "armada_agent"

    def _on_relation_changed(self, event):
        if self._relation.data[self.model.app]["status"]:
            logger.info("## Starting Armada agent")
            self._charm._armada_agent_ops.systemctl("start")
            self._charm.unit.status = ActiveStatus("armada agent started")

        logger.info("## Armada agent wasn't started")

    def _on_relation_broken(self, event):
        """Stops the daemon service"""

        logger.info("## Stopping Armada agent")
        self._charm._armada_agent_ops.systemctl("stop")
        self._charm.unit.status = WaitingStatus("armada agent stopped")

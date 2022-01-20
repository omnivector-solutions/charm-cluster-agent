import logging

from ops.framework import Object
from ops.model import WaitingStatus, ActiveStatus


logger = logging.getLogger()


class UserGroupRequires(Object):
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
            self._charm.on[self._relation_name].relation_departed,
            self._on_relation_departed,
        )
        self.framework.observe(
            self._charm.on[self._relation_name].relation_broken,
            self._on_relation_broken,
        )

    @property
    def _relation(self):
        return self.framework.model.get_relation(self._relation_name)

    def _set_relation_data(self):
        """Configure the relation data"""
        self._relation.data[self.model.app]["user_name"] = self._charm.cluster_agent_ops.CLUSTER_AGENT_USER
        self._relation.data[self.model.app]["user_uid"] = self._charm.cluster_agent_ops.CLUSTER_AGENT_USER_UID
        self._relation.data[self.model.app]["group_name"] = self._charm.cluster_agent_ops.CLUSTER_AGENT_GROUP

    def _on_relation_created(self, event):
        """Create the user and group sent by the provides side of the relation."""
        self._set_relation_data()

    def _on_relation_changed(self, event):
        """Sets the user_created flag as true"""
        if event.relation.data.get(event.app):
            if "success" in event.relation.data[event.app].get("status", "failure"):
                self._charm.stored.user_created = True

        self._charm.cluster_agent_ops.start_agent()
        self._charm.unit.status = ActiveStatus("cluster agent started")

    def _on_relation_departed(self, event):
        """Sends data to the other side of the relation"""
        self._set_relation_data()

    def _on_relation_broken(self, event):
        """Stops the daemon service"""

        logger.info("## Stopping Cluster agent")
        self._charm.cluster_agent_ops.stop_agent()
        self._charm.unit.status = WaitingStatus("cluster agent stopped. Waiting slurmctld relation")

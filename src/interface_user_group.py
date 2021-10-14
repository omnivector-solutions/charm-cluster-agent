from ops.framework import EventBase, EventSource, Object, ObjectEvents


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

    @property
    def _relation(self):
        return self.framework.model.get_relation(self._relation_name)

    def _on_relation_created(self, event):
        """Create the user and group sent by the provides side of the relation."""
        self._relation.data[self.model.app]['user'] = "armada_agent"
        self._relation.data[self.model.app]['group'] = "armada_agent"

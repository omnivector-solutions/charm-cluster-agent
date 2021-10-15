# charm-armada-agent


# Usage
Follow the steps below to get started.

### Build the charm

Running the following command will produce a .charm file, `armada-agent.charm`
```bash
charmcraft build
```

### Create the armada-agent charm config

`armada-agent.yaml`

```yaml
armada-agent:
  api-key: "<backend api-key>"
  backend-url: "<backend-url>"
  aws-access-key-i: "<aws-access-key-i>"
  aws-secret-access-key: "<aws-secret-access-key>"
```

e.g.

```yaml
armada-agent:
  backend-url: https://armada-k8s-staging.omnivector.solutions
  api-key: GJGXBnzhyt8zKiVV5s9sW9pONOBa4sTW2VUd0VPK
  aws-access-key-id: ABCDEFGHIJKLMN
  aws-secret-access-key: g3iyVyBPo93k8RwBNCW4r6T7tst0TaO5+928i4vt
```

### Deploy the charm
Using the built charm and the defined config, run the command to deploy the charm.
```bash
juju deploy ./armada-agent.charm \
    --config ./armada-agent.yaml \
    --series centos7
```

### Charm Actions
The armada-agent charm exposes additional functionality to facilitate armada-agent
package upgrades.

To upgrade the armada-agent to a new version or release:
```bash
juju run-action armada-agent/leader upgrade version="7.7.7"
```

This will result in the armada-agent package upgrade to 7.7.7.

#### License
* MIT (see `LICENSE` file in this directory for full preamble)

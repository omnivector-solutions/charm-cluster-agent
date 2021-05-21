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
  jwt: "<slurmrestd-jwt>"
  api-key: "<backend api-key>"
  backend-url: "<backend-url>"
  pypi-url: "<pypi-url>"
  pypi-username: "<pypi-username>"
  pypi-password: "<pypi-password>"
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

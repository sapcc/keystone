# Run Keystone On Your Local Machine

This document aims to be as detailed as possible to enable you to run your own
Keystone instance locally on your machine. This might be necessary if you need
to test Keystone extensions or if you want to run test in Keystone itself.

This guide assumes you have a macos system.

**clone keystone from git to a custom folder:**
```shell
git clone https://github.com/sapcc/keystone.git keystone-local-setup
```

**you might want to switch to a different branch:**
```
git switch <branch>
```

## Nix development shell

Nix provides Python 3.12, tox, Git, a C compiler, OpenLDAP, OpenSSL, SASL,
PostgreSQL client libraries and build tools, memcached, telnet and xmlsec1.
It also exports the test `OS_*` variables shown below and preserves the native
build environment for tox. `flake.lock` pins the Nix tools.

From the repository root, enter the development shell:

```shell
nix develop
```

Alternatively, if you use direnv with Nix flake support, load the Nix
environment in your existing shell:

```shell
direnv allow
```

Nix only provides the prerequisites; it does not install Python dependencies,
activate a virtualenv or launch a nested shell. After changes to `flake.nix`,
run `direnv reload` if you use direnv.

Run Keystone commands through the `venv` tox environment:

```shell
tox -e venv -- keystone-manage --help
tox -e venv -- keystone-status --help
```

The first setup requires network access, and subsequent runs 
reuse the environment and update dependencies when needed. 
To prepare it without running a command, use `tox -e venv --notest`.

uWSGI and the OpenStack CLI are optional local-running tools, not dependencies
of the existing `venv` environment. The examples below use tox 4's
`--override` option to add the required tool for that invocation without
editing `tox.ini`. The Nix shell supplies tox 4.

In another development-shell terminal, start memcached in the foreground
(stop it with Ctrl-C):

```shell
memcached -l 127.0.0.1 -p 11211 -U 0
```

Continue with **run config generator or write minimal config** below. The
MariaDB Docker command requires the Docker CLI and a running Docker daemon
(for example, Docker Desktop on macOS). Once the Fernet key directory belongs
to your user, run `tox -e venv -- keystone-manage fernet_setup` without `sudo`.


## Homebrew setup

**install openldap and memcached:**
```shell
brew install openldap
brew install memcached
brew services start memcached
# brew services restart memcached
# brew services stop memcached
```

**check if memcached is running:**
```
telnet localhost 11211

Trying 127.0.0.1...
Connected to localhost.
Escape character is '^]'.
quit
Connection closed by foreign host.
```

this would be an error:
```
telnet localhost 11211

Trying 127.0.0.1...
telnet: connect to address 127.0.0.1: Connection refused
Trying ::1...
telnet: connect to address ::1: Connection refused
telnet: Unable to connect to remote host
```

**install dependencies:**
```shell
export \
  LDFLAGS="-L$(brew --prefix openssl)/lib \
           -L$(brew --prefix openldap)/lib" \
  CFLAGS="-I$(brew --prefix openssl)/include \
          -I$(brew --prefix openldap)/include" \
  CPPFLAGS="-I$(brew --prefix openssl)/include \
            -I$(brew --prefix openldap)/include"

uv pip install -r custom-requirements.txt -c https://releases.openstack.org/constraints/upper/master -e . uwsgi pymysql
```

## Configure and run Keystone

The commands below use tox to run inside `.tox/venv` without activating it or
starting another shell. Python and tox must be available, along with the
native dependencies provided by the Nix shell or your non-Nix setup.

**run config generator or write minimal config:**
```shell
tox -e venv -- oslo-config-generator --config-file=config-generator/keystone.conf
```
you will find a sample config in `etc/etc/keystone.conf.sample`

**minimal config:**
```config
[DEFAULT]

[database]
connection = mysql+pymysql://keystone:keystone@127.0.0.1/keystone?charset=utf8

[token]
provider = fernet

[lifesaver]
enabled = true
memcached = 127.0.0.1:11211
# deprecated
domain_whitelist = tempest
domain_allowlist = tempest
# deprecated
user_whitelist = admin, keystone, nova, neutron, cinder, glance, designate, barbican, dashboard, manila, swift
initial_credit = 20
refill_seconds = 60
refill_amount = 5
status_cost = default:1,401:10,403:5,404:0
token_cost = default:1,401:10,403:5,404:10
```

if you want to use the sample config please change the same entries like in the minimal config.

save the config under `/etc/keystone/keystone.conf` and set permissions:

```shell
chmod 640 /etc/keystone/keystone.conf
```

**Initialize Fernet Keys:**
```shell
sudo mkdir -p /etc/keystone/fernet-keys/
sudo chown -R <user>:staff /etc/keystone/fernet-keys
```

Generate and initialize Fernet keys. Keystone comes with utilities to help you manage Fernet keys. Use the following command to create and distribute the keys:

```shell
tox -e venv -- keystone-manage fernet_setup
```

**Configure Permissions:**
Ensure that the directory and its contents are accessible by the user under which your uWSGI or Keystone process is running. Adjust permissions as necessary:

```shell
sudo chmod 0700 /etc/keystone/fernet-keys/
```



**Run MariaDB docker database:**
```shell
docker run \
  --rm \
  -p 3306:3306 \
  --hostname keystone-mariadb --name keystone-mariadb \
  --env MARIADB_USER=keystone --env MARIADB_PASSWORD=keystone --env MARIADB_DATABASE=keystone \
  --env MARIADB_ROOT_PASSWORD=insecure_slave \
  keppel.eu-de-1.cloud.sap/ccloud-dockerhub-mirror/library/mariadb:latest
```

**prepare database:**
```shell
tox -e venv -- keystone-manage db_sync
```


**add sample data:**
```shell
tox -e venv --override 'testenv.deps+=python-openstackclient' -- bash -c \
  'DISABLE_ENDPOINTS=true KEYSTONE_PORT=8000 ADMIN_PASSWORD=s3cr3t bash tools/sample_data.sh'
```

output will look like this:

```
tox -e venv --override 'testenv.deps+=python-openstackclient' -- bash -c 'DISABLE_ENDPOINTS=true KEYSTONE_PORT=8000 ADMIN_PASSWORD=s3cr3t bash tools/sample_data.sh'

2026-01-06 10:13:37.432 86703 INFO keystone.cmd.bootstrap [None req-0fa06c44-3bfc-486a-9db5-65cd62e2bd6e - - - - - -] Created domain default
2026-01-06 10:13:37.501 86703 INFO keystone.cmd.bootstrap [None req-0fa06c44-3bfc-486a-9db5-65cd62e2bd6e - - - - - -] Created project admin
2026-01-06 10:13:37.527 86703 WARNING keystone.common.password_hashing [None req-0fa06c44-3bfc-486a-9db5-65cd62e2bd6e - - - - - -] Truncating password to algorithm specific maximum length 72 characters.: keystone.exception.UserNotFound: Could not find user: admin.
2026-01-06 10:13:37.740 86703 INFO keystone.cmd.bootstrap [None req-0fa06c44-3bfc-486a-9db5-65cd62e2bd6e - - - - - -] Created user admin
...
```

**running the local keystone instance:**
```shell
tox -e venv --override 'testenv.deps+=uwsgi' -- uwsgi --http 127.0.0.1:8000 --eval "from keystone.server.wsgi import initialize_public_application; application = initialize_public_application()"
# Or use the WSGI script installed in the tox environment:
tox -e venv --override 'testenv.deps+=uwsgi' -- uwsgi --http 127.0.0.1:8000 --wsgi-file .tox/venv/bin/keystone-wsgi-public
```

**use these test environment vars:**
```shell
export \
OS_AUTH_URL=http://localhost:8000/v3 \
OS_IDENTITY_API_VERSION=3 \
OS_PASSWORD=s3cr3t \
OS_PROJECT_DOMAIN_ID=default \
OS_PROJECT_NAME=admin \
OS_USERNAME=admin \
OS_USER_DOMAIN_ID=default
```

**test keystone instance with this command:**
```shell
tox -e venv --override 'testenv.deps+=python-openstackclient' \
  --override 'testenv.passenv+=OS_*' -- openstack user list
```

the output should look similar to this:
```
+----------------------------------+-------+
| ID                               | Name  |
+----------------------------------+-------+
| 786c5d9c6dfe4dd2a08d8156ffaa68e7 | admin |
+----------------------------------+-------+
```
## Linting, formatting and tests

Run these commands from the repository root with the Nix environment loaded.
Tox creates separate environments under `.tox` and installs the dependencies
from `tox.ini`, including `test-requirements.txt` and the custom requirements.
You do not need to prepare the `venv` environment first for these checks: use
direnv, or run a command directly, for example
`nix develop --command tox -e pep8`.
The first run requires network access; pre-commit also downloads its pinned
hooks. Pre-commit is installed by the `pep8` tox environment, not by Nix.

### Linting

Run the full lint suite configured in the `pep8` tox environment:

```shell
tox -e pep8
```

This runs all hooks in `.pre-commit-config.yaml` (including Ruff, formatting,
Hacking, Bandit and mypy), followed by Bashate on `devstack/plugin.sh`.
To run only the pre-commit hooks, prepare the `pep8` environment without running
its checks, then invoke its pre-commit executable directly. This setup still
installs the environment's test dependencies:

```shell
tox -e pep8 --notest
.tox/pep8/bin/pre-commit run --all-files --show-diff-on-failure
```

**These checks can modify files.** In particular, the Ruff lint hook enables
both `--fix` and `--unsafe-fixes`. Review the diff and rerun the checks after
fixes; pre-commit reports a failure when a hook changes files.

### Formatting

Use the repository's pinned Ruff formatter through pre-commit in the `pep8`
environment rather than a separately installed version:

```shell
tox -e pep8 --notest
.tox/pep8/bin/pre-commit run ruff-format --all-files
# Or format only specific files:
.tox/pep8/bin/pre-commit run ruff-format --files keystone/common/utils.py
```

### Unit tests

Run the unit suite with the shell's Python 3.12:

```shell
tox -e py312
```

Pass a test name or regular expression after `--` to run a subset:

```shell
tox -e py312 -- keystone.tests.unit.test_auth_plugin
# Limit workers if the full suite uses too much memory:
tox -e py312 -- --concurrency 2
```

The default test path is `keystone/tests/unit`, as configured in `.stestr.conf`.
These tests do not require the locally running Keystone instance described
below. Database migration tests use opportunistic MySQL/PostgreSQL fixtures
and may be skipped when suitable databases are unavailable.

For coverage or the protection suite:

```shell
tox -e cover
tox -e protection
```

Coverage reports are written to `cover/`. See
[`doc/source/contributor/testing-keystone.rst`](doc/source/contributor/testing-keystone.rst)
for additional testing options.

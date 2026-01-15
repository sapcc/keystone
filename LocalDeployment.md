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

**install openldap and memcached:**
```shell
brew install openldap
brew install memcached
brew services start memcached
# brew services restart memcached
# brew services stop memcached
```

**set environment variables:**
```shell
export \
  LDFLAGS="-L$(brew --prefix openssl)/lib \
           -L$(brew --prefix openldap)/lib" \
  CFLAGS="-I$(brew --prefix openssl)/include \
          -I$(brew --prefix openldap)/include"
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

**setup python virtual environment with `uv`:**
```shell
uv venv --python 3.12 --prompt "venv"
```

**activate the virtual environment:**
```shell
source .venv/bin/activate
```

**install dependencies:**
```shell
uv pip install -r custom-requirements.txt

# latest dependencies
uv pip install -c https://releases.openstack.org/constraints/upper/master -e .

# needed to run locally
uv pip install uwsgi

# needed for mysql database connection
uv pip install pymysql
```

**run config generator or write minimal config:**
```shell
oslo-config-generator --config-file=config-generator/keystone.conf
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
sudo keystone-manage fernet_setup
```

**Configure Permissions:**
Ensure that the directory and its contents are accessible by the user under which your uWSGI or Keystone process is running. Adjust permissions as necessary:

```shell
sudo chmod 0700 /etc/keystone/fernet-keys/
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

**Run MySQL docker database:**
```shell
docker run -d --rm --name keystone-mysql \
  -p 3306:3306 \
  --hostname keystone-mysql --name keystone-mysql \
  --env MYSQL_USER=keystone --env MYSQL_PASSWORD=keystone --env MYSQL_DATABASE=keystone \
  --env MYSQL_ROOT_PASSWORD=insecure_slave \
  mysql:8.4
```

**prepare database:**
```shell
keystone-manage db_sync
```


**add sample data:**
```shell
DISABLE_ENDPOINTS=true KEYSTONE_PORT=8000 ADMIN_PASSWORD=s3cr3t tools/sample_data.sh
```

output will look like this:

```
DISABLE_ENDPOINTS=true KEYSTONE_PORT=8000 ADMIN_PASSWORD=s3cr3t tools/sample_data.sh 

2026-01-06 10:13:37.432 86703 INFO keystone.cmd.bootstrap [None req-0fa06c44-3bfc-486a-9db5-65cd62e2bd6e - - - - - -] Created domain default
2026-01-06 10:13:37.501 86703 INFO keystone.cmd.bootstrap [None req-0fa06c44-3bfc-486a-9db5-65cd62e2bd6e - - - - - -] Created project admin
2026-01-06 10:13:37.527 86703 WARNING keystone.common.password_hashing [None req-0fa06c44-3bfc-486a-9db5-65cd62e2bd6e - - - - - -] Truncating password to algorithm specific maximum length 72 characters.: keystone.exception.UserNotFound: Could not find user: admin.
2026-01-06 10:13:37.740 86703 INFO keystone.cmd.bootstrap [None req-0fa06c44-3bfc-486a-9db5-65cd62e2bd6e - - - - - -] Created user admin
2026-01-06 10:13:37.748 86703 INFO keystone.cmd.bootstrap [None req-0fa06c44-3bfc-486a-9db5-65cd62e2bd6e - - - - - -] Created role reader
2026-01-06 10:13:37.753 86703 INFO keystone.cmd.bootstrap [None req-0fa06c44-3bfc-486a-9db5-65cd62e2bd6e - - - - - -] Created role member
2026-01-06 10:13:37.759 86703 INFO keystone.cmd.bootstrap [None req-0fa06c44-3bfc-486a-9db5-65cd62e2bd6e - - - - - -] Created implied role where aba2a46bda9347f7a7dc916c0ee703e3 implies dde10fc1b79b44a9a12d68ba7a541093
2026-01-06 10:13:37.763 86703 INFO keystone.cmd.bootstrap [None req-0fa06c44-3bfc-486a-9db5-65cd62e2bd6e - - - - - -] Created role manager
2026-01-06 10:13:37.769 86703 INFO keystone.cmd.bootstrap [None req-0fa06c44-3bfc-486a-9db5-65cd62e2bd6e - - - - - -] Created implied role where c96522926d1d4b28baa1811085a83d93 implies aba2a46bda9347f7a7dc916c0ee703e3
2026-01-06 10:13:37.773 86703 INFO keystone.cmd.bootstrap [None req-0fa06c44-3bfc-486a-9db5-65cd62e2bd6e - - - - - -] Created role admin
2026-01-06 10:13:37.780 86703 INFO keystone.cmd.bootstrap [None req-0fa06c44-3bfc-486a-9db5-65cd62e2bd6e - - - - - -] Created implied role where 260c8151ce564bcb9c227adea8ff7908 implies c96522926d1d4b28baa1811085a83d93
2026-01-06 10:13:37.785 86703 INFO keystone.cmd.bootstrap [None req-0fa06c44-3bfc-486a-9db5-65cd62e2bd6e - - - - - -] Created role service
2026-01-06 10:13:37.792 86703 INFO keystone.cmd.bootstrap [None req-0fa06c44-3bfc-486a-9db5-65cd62e2bd6e - - - - - -] Granted role admin on project admin to user admin.
2026-01-06 10:13:37.796 86703 INFO keystone.cmd.bootstrap [None req-0fa06c44-3bfc-486a-9db5-65cd62e2bd6e - - - - - -] Granted role admin on the system to user admin.
2026-01-06 10:13:37.800 86703 WARNING py.warnings [None req-0fa06c44-3bfc-486a-9db5-65cd62e2bd6e - - - - - -] /Users/I761196/dev/sci/keystone-local-test-delete-after/.venv/lib/python3.12/site-packages/pycadf/identifier.py:70: UserWarning: Invalid uuid: RegionOne. To ensure interoperability, identifiers should be a valid uuid.
  warnings.warn(('Invalid uuid: %s. To ensure interoperability, '

2026-01-06 10:13:37.801 86703 INFO keystone.cmd.bootstrap [None req-0fa06c44-3bfc-486a-9db5-65cd62e2bd6e - - - - - -] Created region RegionOne
2026-01-06 10:13:37.810 86703 INFO keystone.cmd.bootstrap [None req-0fa06c44-3bfc-486a-9db5-65cd62e2bd6e - - - - - -] Created public endpoint http://localhost:8000/v3
2026-01-06 10:13:37.815 86703 INFO keystone.cmd.bootstrap [None req-0fa06c44-3bfc-486a-9db5-65cd62e2bd6e - - - - - -] Created internal endpoint http://localhost:8000/v3
2026-01-06 10:13:37.820 86703 INFO keystone.cmd.bootstrap [None req-0fa06c44-3bfc-486a-9db5-65cd62e2bd6e - - - - - -] Created admin endpoint http://localhost:8000/v3
Failed to discover available identity versions when contacting http://localhost:8000/v3. Attempting to parse version from URL.
Unable to establish connection to http://localhost:8000/v3/auth/tokens: HTTPConnectionPool(host='localhost', port=8000): Max retries exceeded with url: /v3/auth/tokens (Caused by NewConnectionError('<urllib3.connection.HTTPConnection object at 0x108b73ed0>: Failed to establish a new connection: [Errno 61] Connection refused'))
Failed to discover available identity versions when contacting http://localhost:8000/v3. Attempting to parse version from URL.
Unable to establish connection to http://localhost:8000/v3/auth/tokens: HTTPConnectionPool(host='localhost', port=8000): Max retries exceeded with url: /v3/auth/tokens (Caused by NewConnectionError('<urllib3.connection.HTTPConnection object at 0x10cf8bed0>: Failed to establish a new connection: [Errno 61] Connection refused'))
Failed to discover available identity versions when contacting http://localhost:8000/v3. Attempting to parse version from URL.
Unable to establish connection to http://localhost:8000/v3/auth/tokens: HTTPConnectionPool(host='localhost', port=8000): Max retries exceeded with url: /v3/auth/tokens (Caused by NewConnectionError('<urllib3.connection.HTTPConnection object at 0x10c82fed0>: Failed to establish a new connection: [Errno 61] Connection refused'))
Failed to discover available identity versions when contacting http://localhost:8000/v3. Attempting to parse version from URL.
Unable to establish connection to http://localhost:8000/v3/auth/tokens: HTTPConnectionPool(host='localhost', port=8000): Max retries exceeded with url: /v3/auth/tokens (Caused by NewConnectionError('<urllib3.connection.HTTPConnection object at 0x10a723ed0>: Failed to establish a new connection: [Errno 61] Connection refused'))
...
```

**running the local keystone instance:**
```shell
uwsgi --http 127.0.0.1:8000 --eval "from keystone.server.wsgi import initialize_public_application; application = initialize_public_application()"
```

**test keystone instance with this command:**
```shell
openstack user list
```

the output should look similar to this:
```
+----------------------------------+-------+
| ID                               | Name  |
+----------------------------------+-------+
| 786c5d9c6dfe4dd2a08d8156ffaa68e7 | admin |
+----------------------------------+-------+
```
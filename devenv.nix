{ pkgs, lib, config, ... }:

let
  keystoneSettings = state: {
    DEFAULT = { };
    database.connection = "mysql+pymysql://keystone:keystone@127.0.0.1:3306/keystone?charset=utf8";
    identity.driver = "sql";
    token.provider = "fernet";
    fernet_tokens.key_repository = "${state}/keystone/fernet-keys";
    credential.key_repository = "${state}/keystone/credential-keys";
    lifesaver = {
      enabled = true;
      memcached = "127.0.0.1:11211";
      domain_whitelist = "tempest";
      domain_allowlist = "tempest";
      user_whitelist = "admin, keystone, nova, neutron, cinder, glance, designate, barbican, dashboard, manila, swift";
      initial_credit = 20;
      refill_seconds = 60;
      refill_amount = 5;
      status_cost = "default:1,401:10,403:5,404:0";
      token_cost = "default:1,401:10,403:5,404:10";
    };
  };

  toxEnvironment = ''
    # Compiler wrappers need their role markers to use the Nix flags.
    # Apply this to every tox invocation, including non-interactive tasks.
    export TOX_OVERRIDE="''${TOX_OVERRIDE:+$TOX_OVERRIDE;}testenv.passenv+=NIX_CC_WRAPPER_TARGET_*,NIX_BINTOOLS_WRAPPER_TARGET_*,NIX_CFLAGS_COMPILE*,NIX_LDFLAGS*,PKG_CONFIG_PATH,LD_LIBRARY_PATH,PYTHONNOUSERSITE,TOX_OVERRIDE,OS_*"
    # Provision the uv plugin without changing the project's tox configuration.
    export TOX_OVERRIDE="$TOX_OVERRIDE;tox.requires=tox>=4,tox-uv-bare>=1"
  '' + lib.optionalString pkgs.stdenv.hostPlatform.isLinux ''
    # PyPI wheels may need the C++ runtime outside Nix's RPATHs.
    export LD_LIBRARY_PATH="${lib.makeLibraryPath [ pkgs.stdenv.cc.cc.lib ]}''${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
  '';

  # Keep bootstrap credentials and catalog endpoints aligned with the CLI.
  initializeKeystone = ''
    set -e

    keystone-manage fernet_setup
    keystone-manage credential_setup
    keystone-manage db_sync
    keystone-manage bootstrap \
      --bootstrap-username "$OS_USERNAME" \
      --bootstrap-password "$OS_PASSWORD" \
      --bootstrap-project-name "$OS_PROJECT_NAME" \
      --bootstrap-admin-url "$OS_AUTH_URL" \
      --bootstrap-public-url "$OS_AUTH_URL" \
      --bootstrap-internal-url "$OS_AUTH_URL"
  '';

  initializeLdapDomain = pkgs.writeText "initialize-ldap-domain.py" ''
    import os
    import uuid
    from keystone import exception
    from keystone.common import provider_api
    from keystone.server import backends, configure

    configure(config_files=[os.environ["OS_KEYSTONE_CONFIG_FILES"]])
    backends.load_backends()
    resources = provider_api.ProviderAPIs.resource_api
    try:
        resources.get_domain_by_name("LDAP")
    except exception.DomainNotFound:
        domain_id = uuid.uuid4().hex
        resources.create_domain(domain_id, {
            "id": domain_id,
            "name": "LDAP", "enabled": True,
            "description": "Local 389 Directory Server identities",
        })
    print("Keystone LDAP domain initialized")
  '';
in
{
  name = "keystone";
  imports = [ ./devenv/dirsrv.nix ];

  files.".devenv/keystone/sql/keystone.conf".ini = keystoneSettings config.devenv.state;

  # Keep dependency installation and virtual environments managed by tox.
  languages.python = {
    enable = true;
    package = pkgs.python312;
    lsp.enable = false;
    uv.enable = true;
  };

  # devenv's mkShell supplies the compiler and header/linker flags for native
  # extensions, including python-ldap, scrypt, cffi and uWSGI.
  packages = with pkgs; [
    python312Packages.tox
    git
    memcached
    inetutils # telnet, for checking memcached
    xmlsec # xmlsec1, used by pysaml2
    pkg-config
    libpq.pg_config # psycopg2, required by test-requirements.txt
    openldap
    openssl
    cyrus_sasl
    libffi
    libpq
  ];

  env = {
    PYTHONNOUSERSITE = "1";
    TOX_UV_PATH = "${pkgs.uv}/bin/uv";
    OS_KEYSTONE_CONFIG_FILES = lib.mkDefault (toString config.files.".devenv/keystone/sql/keystone.conf".file);

    OS_AUTH_URL = "http://localhost:8000/v3";
    OS_IDENTITY_API_VERSION = "3";
    OS_PASSWORD = "s3cr3t";
    OS_PROJECT_DOMAIN_ID = "default";
    OS_PROJECT_NAME = "admin";
    OS_USERNAME = "admin";
    OS_USER_DOMAIN_ID = "default";
  };

  scripts = {
    keystone-manage.exec = ''
      exec tox -e venv -- keystone-manage --config-file "$OS_KEYSTONE_CONFIG_FILES" "$@"
    '';

    keystone-status.exec = ''
      exec tox -e venv -- keystone-status --config-file "$OS_KEYSTONE_CONFIG_FILES" "$@"
    '';

    keystone-python.exec = ''
      exec tox -e venv -- python "$@"
    '';

    start.exec = initializeKeystone + ''
      exec tox -e venv \
        --override 'testenv.deps+=uwsgi' \
        -- uwsgi \
        --http 127.0.0.1:8000 \
        --master \
        --processes 1 \
        --lazy-apps \
        --enable-threads \
        --single-interpreter \
        --module 'keystone.server.wsgi:initialize_public_application()' \
        "$@"
    '';

    debugger.exec = initializeKeystone + ''
      exec tox -e venv \
        --override 'testenv.deps+=uwsgi' \
        --override 'testenv.deps+=debugpy' \
        -- uwsgi \
        --http 127.0.0.1:8000 \
        --master \
        --processes 1 \
        --lazy-apps \
        --enable-threads \
        --single-interpreter \
        --eval "import os, debugpy; debugpy.configure(python=os.path.abspath('.tox/venv/bin/python'), subProcess=False); debugpy.listen(('127.0.0.1', 5678)); print('Waiting for Zed on port 5678...', flush=True); debugpy.wait_for_client(); from keystone.server.wsgi import initialize_public_application; application = initialize_public_application()" \
        "$@"
    '';
  };

  profiles.sql.module = {
    services.mysql = {
      enable = true; # Uses MariaDB by default.
      settings.mysqld = {
        bind-address = "127.0.0.1";
        port = 3306;
      };
      initialDatabases = [ { name = "keystone"; } ];
      ensureUsers = [
        {
          name = "keystone";
          host = "127.0.0.1";
          password = "keystone";
          ensurePermissions."keystone.*" = "ALL PRIVILEGES";
        }
      ];
    };

    services.memcached = {
      enable = true;
      bind = "127.0.0.1";
      port = 11211;
      startArgs = [ "-U" "0" ];
    };

    tasks."sql:initialize" = {
      description = "Sync the Keystone database and bootstrap the admin account";
      # Wait for the service to create the database and grant permissions too.
      after = [ "devenv:mysql:configure" ];
      wantedBy = [ "devenv:processes:mysql" ];
      exec = toxEnvironment + initializeKeystone;
      showOutput = true;
    };
  };

  profiles.ldap = {
    extends = [ "sql" ];
    module = { config, ... }: {
      files.".devenv/keystone/ldap/keystone.conf".ini =
        (keystoneSettings config.devenv.state) // {
          identity = {
            driver = "sql";
            domain_specific_drivers_enabled = true;
            domain_configurations_from_database = false;
            domain_config_dir = "${config.devenv.root}/.devenv/keystone/ldap/domains";
          };
        };

      files.".devenv/keystone/ldap/domains/keystone.LDAP.conf".ini = {
        identity.driver = "ldap";
        ldap = {
          url = config.env.LDAPURI;
          user = config.env.LDAPBINDDN;
          password = config.services.dirsrv.directoryManagerPassword;
          suffix = config.env.LDAPBASE;
          user_tree_dn = "ou=Users,${config.env.LDAPBASE}";
          user_objectclass = "inetOrgPerson";
          user_id_attribute = "uid";
          user_name_attribute = "uid";
          user_enabled_attribute = "nsAccountLock";
          user_enabled_invert = true;
          user_enabled_default = "False";
          group_tree_dn = "ou=Groups,${config.env.LDAPBASE}";
          group_objectclass = "groupOfNames";
          group_id_attribute = "cn";
          group_name_attribute = "cn";
          group_member_attribute = "member";
        };
      };

      env = {
        OS_KEYSTONE_CONFIG_FILES = toString config.files.".devenv/keystone/ldap/keystone.conf".file;
        LDAPURI = "ldap://127.0.0.1:3389";
        LDAPBINDDN = "cn=Directory Manager";
        LDAPBASE = "dc=example,dc=com";
      };

      services.dirsrv = {
        enable = true;
        containerName = "keystone-ldap";
        directoryManagerPassword = "keystone";
      };

      tasks."ldap:initialize" = {
        description = "Create the directory suffix and LDAP-backed Keystone domain";
        after = [ "devenv:processes:ldap@ready" "sql:initialize" "devenv:files" ];
        wantedBy = [ "devenv:processes:ldap" ];
        exec = toxEnvironment + ''
          set -e
          ldapArgs=(-x -H "$LDAPURI" -D "$LDAPBINDDN" -w ${lib.escapeShellArg config.services.dirsrv.directoryManagerPassword})

          if ! ldapsearch "''${ldapArgs[@]}" -b "$LDAPBASE" -s base dn >/dev/null 2>&1; then
            docker exec ${lib.escapeShellArg config.services.dirsrv.containerName} \
              dsconf localhost backend create --suffix "$LDAPBASE" --be-name userroot --create-suffix
          fi

          for ou in Users Groups; do
            if ! ldapsearch "''${ldapArgs[@]}" -b "ou=$ou,$LDAPBASE" -s base dn >/dev/null 2>&1; then
              ldapadd "''${ldapArgs[@]}" <<LDIF
          dn: ou=$ou,$LDAPBASE
          objectClass: organizationalUnit
          ou: $ou
          LDIF
            fi
          done

          keystone-python ${initializeLdapDomain}
        '';
        showOutput = true;
      };
    };
  };

  enterShell = toxEnvironment;
}

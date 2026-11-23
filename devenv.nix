{ pkgs, lib, ... }:

let
  # Keep bootstrap credentials and catalog endpoints aligned with the CLI.
  initializeKeystone = ''
    set -e

    keystone-manage db_sync
    keystone-manage bootstrap \
      --bootstrap-username "$OS_USERNAME" \
      --bootstrap-password "$OS_PASSWORD" \
      --bootstrap-project-name "$OS_PROJECT_NAME" \
      --bootstrap-admin-url "$OS_AUTH_URL" \
      --bootstrap-public-url "$OS_AUTH_URL" \
      --bootstrap-internal-url "$OS_AUTH_URL"
  '';
in
{
  name = "keystone";

  # Keep dependency installation and virtual environments managed by tox.
  languages.python = {
    enable = true;
    package = pkgs.python312;
    lsp.enable = false;
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
      exec tox -e venv -- keystone-manage "$@"
    '';

    keystone-status.exec = ''
      exec tox -e venv -- keystone-manage "$@"
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

    mariadb.exec = ''
      exec docker run \
        --rm \
        -p 3306:3306 \
        --hostname keystone-mariadb --name keystone-mariadb \
        --env MARIADB_USER=keystone --env MARIADB_PASSWORD=keystone --env MARIADB_DATABASE=keystone \
        --env MARIADB_ROOT_PASSWORD=insecure_slave \
        mariadb:latest "$@"
    '';
  };

  enterShell = ''
    # Compiler wrappers need their role markers to use the Nix flags.
    # Apply this to every tox invocation.
    export TOX_OVERRIDE="''${TOX_OVERRIDE:+$TOX_OVERRIDE;}testenv.passenv+=NIX_CC_WRAPPER_TARGET_*,NIX_BINTOOLS_WRAPPER_TARGET_*,NIX_CFLAGS_COMPILE*,NIX_LDFLAGS*,PKG_CONFIG_PATH,LD_LIBRARY_PATH,PYTHONNOUSERSITE,TOX_OVERRIDE,OS_*"
  '' + lib.optionalString pkgs.stdenv.hostPlatform.isLinux ''
    # PyPI wheels may need the C++ runtime outside Nix's RPATHs.
    export LD_LIBRARY_PATH="${lib.makeLibraryPath [ pkgs.stdenv.cc.cc.lib ]}''${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
  '';
}

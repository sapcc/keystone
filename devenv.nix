{ pkgs, lib, ... }:

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

  enterShell = ''
    # Compiler wrappers need their role markers to use the Nix flags.
    # Apply this to every tox invocation.
    export TOX_OVERRIDE="''${TOX_OVERRIDE:+$TOX_OVERRIDE;}testenv.passenv+=NIX_CC_WRAPPER_TARGET_*,NIX_BINTOOLS_WRAPPER_TARGET_*,NIX_CFLAGS_COMPILE*,NIX_LDFLAGS*,PKG_CONFIG_PATH,LD_LIBRARY_PATH,PYTHONNOUSERSITE,TOX_OVERRIDE,OS_*"
  '' + lib.optionalString pkgs.stdenv.hostPlatform.isLinux ''
    # PyPI wheels may need the C++ runtime outside Nix's RPATHs.
    export LD_LIBRARY_PATH="${lib.makeLibraryPath [ pkgs.stdenv.cc.cc.lib ]}''${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
  '';
}

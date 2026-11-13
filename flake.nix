{
  description = "Keystone local development environment";

  inputs.nixpkgs.url = "github:nixos/nixpkgs/nixpkgs-unstable";

  outputs = { nixpkgs, ... }:
    let
      systems = [
        "aarch64-darwin"
        "aarch64-linux"
        "x86_64-linux"
      ];
    in
    {
      devShells = nixpkgs.lib.genAttrs systems (system:
        let
          pkgs = import nixpkgs { inherit system; };
          python = pkgs.python312;
        in
        {
          default = pkgs.mkShell {
            packages = with pkgs; [
              python
              python312Packages.tox
              git
              memcached
              inetutils # telnet, for checking memcached
              xmlsec # xmlsec1, used by pysaml2
            ];

            nativeBuildInputs = [
              pkgs.pkg-config
              pkgs.libpq.pg_config # psycopg2, required by test-requirements.txt
            ];
            # mkShell supplies the compiler and header/linker flags for native
            # extensions, including python-ldap, scrypt, cffi and uWSGI.
            buildInputs = with pkgs; [
              openldap
              openssl
              cyrus_sasl
              libffi
              libpq
            ];

            PYTHONNOUSERSITE = "1";

            shellHook = ''
              # Compiler wrappers need their role markers to use the Nix flags.
              # Apply this to every tox invocation.
              export TOX_OVERRIDE="''${TOX_OVERRIDE:+$TOX_OVERRIDE;}testenv.passenv+=NIX_CC_WRAPPER_TARGET_*,NIX_BINTOOLS_WRAPPER_TARGET_*,NIX_CFLAGS_COMPILE*,NIX_LDFLAGS*,PKG_CONFIG_PATH,LD_LIBRARY_PATH,PYTHONNOUSERSITE,TOX_OVERRIDE,OS_*"

              export OS_AUTH_URL=http://localhost:8000/v3
              export OS_IDENTITY_API_VERSION=3
              export OS_PASSWORD=s3cr3t
              export OS_PROJECT_DOMAIN_ID=default
              export OS_PROJECT_NAME=admin
              export OS_USERNAME=admin
              export OS_USER_DOMAIN_ID=default
            '' + pkgs.lib.optionalString pkgs.stdenv.hostPlatform.isLinux ''
              # PyPI wheels may need the C++ runtime outside Nix's RPATHs.
              export LD_LIBRARY_PATH="${pkgs.lib.makeLibraryPath [ pkgs.stdenv.cc.cc.lib ]}''${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
            '';
          };
        });
    };
}

{
  description = "Keystone local development environment";

  inputs.nixpkgs.url = "github:nixos/nixpkgs/nixpkgs-unstable";

  outputs = { nixpkgs, ... }:
    let
      systems = [
        "aarch64-darwin"
        "x86_64-darwin"
        "aarch64-linux"
        "x86_64-linux"
      ];
    in
    {
      devShells = nixpkgs.lib.genAttrs systems (system:
        let
          pkgs = import nixpkgs { inherit system; };
          python = pkgs.python312;
          # Older OpenStack dependencies still import pkg_resources (see tox.ini).
          buildConstraints = pkgs.writeText "keystone-build-constraints.txt" ''
            setuptools<82
          '';
          install = pkgs.writeShellApplication {
            name = "keystone-install";
            runtimeInputs = [ pkgs.uv pkgs.git ];
            text = ''
              exec uv pip install \
                --python "''${VIRTUAL_ENV:?Enter the Keystone dev shell first}/bin/python" \
                --requirement custom-requirements.txt \
                --constraint "$TOX_CONSTRAINTS_FILE" \
                --build-constraint ${buildConstraints} \
                --editable . uwsgi pymysql python-openstackclient 'setuptools<82' "$@"
            '';
          };
        in
        {
          default = pkgs.mkShell {
            packages = with pkgs; [
              python
              uv
              git
              memcached
              docker-client
              inetutils # telnet, for checking memcached
              xmlsec # xmlsec1, used by pysaml2
              install
            ];

            nativeBuildInputs = [ pkgs.pkg-config ];
            # mkShell supplies the compiler and header/linker flags for native
            # extensions, including python-ldap, scrypt, cffi and uWSGI.
            buildInputs = with pkgs; [
              openldap
              openssl
              cyrus_sasl
              libffi
            ];

            UV_PYTHON = python.interpreter;
            UV_PYTHON_DOWNLOADS = "never";
            PYTHONNOUSERSITE = "1";

            shellHook = ''
              export VIRTUAL_ENV="$PWD/.venv"
              if [ ! -d "$VIRTUAL_ENV" ]; then
                uv venv --python "$UV_PYTHON" "$VIRTUAL_ENV"
              fi
              export PATH="$VIRTUAL_ENV/bin:$PATH"

              # Match this branch's test environment rather than upstream master.
              export TOX_CONSTRAINTS_FILE="''${TOX_CONSTRAINTS_FILE:-https://raw.githubusercontent.com/sapcc/requirements/stable/2025.1-m3/upper-constraints.txt}"

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

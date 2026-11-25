{ config, lib, ... }:

let
  cfg = config.services.dirsrv;
in
{
  options.services.dirsrv = {
    enable = lib.mkEnableOption "a Docker-backed 389 Directory Server";

    image = lib.mkOption {
      type = lib.types.str;
      default = "389ds/dirsrv:latest";
      description = "389 Directory Server container image.";
    };

    platform = lib.mkOption {
      type = lib.types.str;
      default = "linux/amd64";
      description = "Container platform; the Docker Hub image is amd64-only.";
    };

    containerName = lib.mkOption {
      type = lib.types.str;
      default = "devenv-ldap";
      description = "Docker container name and hostname.";
    };

    directoryManagerPassword = lib.mkOption {
      type = lib.types.str;
      description = "Development password for cn=Directory Manager; stored in the Nix store.";
    };

    ldapPort = lib.mkOption {
      type = lib.types.port;
      default = 3389;
      description = "LDAP port exposed on 127.0.0.1.";
    };

    ldapsPort = lib.mkOption {
      type = lib.types.port;
      default = 3636;
      description = "LDAPS port exposed on 127.0.0.1.";
    };
  };

  config = lib.mkIf cfg.enable {
    processes.ldap = {
      exec = ''
        set -e
        containerState=$(mktemp -d "$DEVENV_STATE/ldap.XXXXXX")
        cidfile="$containerState/id"

        # Never stop an existing container if creating ours fails.
        cleanup() {
          if [ -s "$cidfile" ]; then
            docker stop --time 5 "$(cat "$cidfile")" >/dev/null || true
          fi
          rm -f "$cidfile"
          rmdir "$containerState"
        }
        trap cleanup EXIT
        trap 'exit 0' INT TERM

        docker run \
          --rm \
          --cidfile "$cidfile" \
          --platform ${lib.escapeShellArg cfg.platform} \
          -p 127.0.0.1:${toString cfg.ldapPort}:3389 \
          -p 127.0.0.1:${toString cfg.ldapsPort}:3636 \
          --hostname ${lib.escapeShellArg cfg.containerName} \
          --name ${lib.escapeShellArg cfg.containerName} \
          --env ${lib.escapeShellArg "DS_DM_PASSWORD=${cfg.directoryManagerPassword}"} \
          ${lib.escapeShellArg cfg.image} &
        wait "$!"
      '';
      ready = {
        exec = "docker exec ${lib.escapeShellArg cfg.containerName} /usr/lib/dirsrv/dscontainer -H";
        period = 2;
        probe_timeout = 10;
        timeout = 300;
      };
      shutdown.grace = 15;
      restart.on = "never";
    };
  };
}

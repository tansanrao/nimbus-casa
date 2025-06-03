{
  description = "Development environment for CS5264";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-25.05";
    talhelper.url = "github:budimanjojo/talhelper";
  };

  outputs = { self, talhelper, nixpkgs, ... }:
    let
      system = "aarch64-darwin";

      pkgs = import nixpkgs {
        inherit system;
        overlays = [
          talhelper.overlays.default
        ];
      };

# Define kernel development packages
      buildPkgs = with pkgs; [
        talosctl
        uv
        age
        cloudflared
        fluxcd
        sops
        go-task
        kubernetes-helm
        helmfile
        jq
        kustomize
        kubectl
        yq-go
        kubeconform
        k9s
        python313
        cilium-cli
        cue
        makejinja
        bash
        talhelper.packages."${system}".default
      ];
    in
    {
      devShells."${system}".default = pkgs.mkShell {
        buildInputs = buildPkgs;
        shellHook = ''
          # Set environment variables based on the current directory as config root
          export KUBERNETES_DIR="$(pwd)/kubernetes"
          export KUBECONFIG="$(pwd)/kubeconfig"
          export SOPS_AGE_KEY_FILE="$(pwd)/age.key"
          export TALOSCONFIG="$(pwd)/kubernetes/bootstrap/talos/clusterconfig/talosconfig"
          # Tells pip to put packages into $PIP_PREFIX instead of the usual locations.
          # See https://pip.pypa.io/en/stable/user_guide/#environment-variables.
          export PIP_PREFIX=$(pwd)/_build/pip_packages
          export PYTHONPATH="$PIP_PREFIX/${pkgs.python313.sitePackages}:$PYTHONPATH"
          export PATH="$PIP_PREFIX/bin:$PATH"
          unset SOURCE_DATE_EPOCH
        '';
      };
    };
}

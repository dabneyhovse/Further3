{
  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs?ref=nixos-unstable";
    nix = {
      url = "github:NixOS/nix";
      inputs = {
        nixpkgs.follows = "nixpkgs";
        nixpkgs-23-11.follows = "nixpkgs";
        nixpkgs-regression.follows = "nixpkgs";
        flake-parts.follows = "flake-parts";
        flake-compat.follows = "flake-compat";
        git-hooks-nix.follows = "git-hooks";
      };
    };
    flake-compat = {
      url = "github:edolstra/flake-compat";
    };
    git-hooks = {
      url = "github:cachix/git-hooks.nix";
      inputs = {
        flake-compat.follows = "flake-compat";
        gitignore.follows = "gitignore";
        nixpkgs.follows = "nixpkgs";
      };
    };
    gitignore = {
      url = "github:hercules-ci/gitignore.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    cachix = {
      url = "github:cachix/cachix";
      inputs = {
        devenv.follows = "devenv";
        flake-compat.follows = "flake-compat";
        git-hooks.follows = "git-hooks";
        nixpkgs.follows = "nixpkgs";
      };
    };
    flake-parts = {
      url = "github:hercules-ci/flake-parts";
      inputs.nixpkgs-lib.follows = "nixpkgs";
    };
    devenv = {
      url = "github:cachix/devenv";
      inputs = {
        cachix.follows = "cachix";
        git-hooks.follows = "git-hooks";
        flake-compat.follows = "flake-compat";
        nix.follows = "nix";
        nixpkgs.follows = "nixpkgs";
      };
    };
  };

  outputs =
    inputs:
    inputs.flake-parts.lib.mkFlake { inherit inputs; } (
      top@{
        config,
        withSystem,
        moduleWithSystem,
        ...
      }:
      {
        imports = [
          inputs.devenv.flakeModule
        ];
        systems = inputs.nixpkgs.lib.systems.flakeExposed;
        perSystem =
          { config, pkgs, ... }:
          {
            devenv = {
              shells.default = {
                devenv.root = "/tmp";
                languages = {
                  python.enable = true;
                };
                packages = with pkgs; [
                    python3Packages.python-telegram-bot
                    python3Packages.yt-dlp
                    python3Packages.python-vlc
                    python3Packages.validators
                ] ++ pkgs.python3Packages.python-telegram-bot.optional-dependencies.callback-data;
                enterShell = ''
                '';
              };
            };
          };
      }
    );
}

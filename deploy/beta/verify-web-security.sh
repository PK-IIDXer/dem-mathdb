#!/bin/sh
# Fail closed on unrecognized toolchain versions or unreadable trust stores.
set -eu
case "$1" in
  go)
    version="$2"
    case "$version" in ''|*[!0-9.]*) exit 1;; esac
    printf '%s\n' "$version" | awk -F. '
      NF != 3 || $1 !~ /^[0-9]+$/ || $2 !~ /^[0-9]+$/ || $3 !~ /^[0-9]+$/ { exit 1 }
      $1 != 1 || $2 < 26 || ($2 == 26 && $3 < 10) || ($2 == 27 && $3 < 3) { exit 1 }
    '
    ;;
  build-info)
    # A replacement belongs to the immediately preceding dep/mod line.
    # Never mistake the original requirement for the linked replacement.
    awk -v intended="$3" '
      function stable(v) {
        return v ~ /^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$/
      }
      BEGIN {
        net = "golang.org/x/net"
        caddy = "github.com/caddyserver/caddy/v2"
      }
      $1 == "dep" || $1 == "mod" {
        current = ""
        if ($2 == net || $2 == caddy) {
          current = $2
          if (++seen[current] != 1 || (NF != 3 && NF != 4)) bad = 1
          path[current] = $2
          version[current] = $3
        }
        next
      }
      $1 == "=>" {
        if (current != "") {
          if (++replaced[current] != 1 || (NF != 3 && NF != 4)) bad = 1
          path[current] = $2
          version[current] = $3
        } else if ($2 == net || $2 == caddy) {
          bad = 1
        }
        current = ""
        next
      }
      { current = "" }
      END {
        if (bad || seen[net] != 1 || seen[caddy] != 1 ||
            path[net] != net || path[caddy] != caddy ||
            !stable(version[net]) || !stable(version[caddy]) ||
            !stable(intended) || version[caddy] != intended) exit 1
        split(substr(version[net], 2), parts, ".")
        if (parts[1] == 0 && parts[2] < 60) exit 1
        print "Linked " net " " version[net]
        print "Linked " caddy " " version[caddy]
      }
    ' "$2"
    ;;
  ca)
    bundle="$2"
    temporary="$(mktemp -d)"
    trap 'rm -rf "$temporary"' EXIT HUP INT TERM
    openssl crl2pkcs7 -nocrl -certfile "$bundle" -out "$temporary/ca.p7b"
    openssl pkcs7 -in "$temporary/ca.p7b" -print_certs -noout > "$temporary/subjects"
    test -s "$temporary/subjects"
    if grep -F 'emSign ECC Root CA - G3' "$temporary/subjects"; then
      echo 'Compromised CA root remains in trust bundle' >&2
      exit 1
    fi
    ;;
  *) exit 1;;
esac

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
